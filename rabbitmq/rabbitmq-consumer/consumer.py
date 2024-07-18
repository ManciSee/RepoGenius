import os
import sys
import subprocess
import json
import time
import pika
import multiprocessing
from multiprocessing import Manager
from groq import Groq
from dotenv import load_dotenv
import shutil  # Add this import for folder deletion
import requests

VALID_EXTENSIONS = [
    'txt', 'md', 'markdown', 'rst', 'py', 'js', 'java', 'c', 'cpp', 'cs', 'go', 'rb', 'php', 'scala', 
    'html', 'htm', 'xml', 'json', 'yaml', 'yml', 'toml', 'cfg', 'conf', 'css', 
    'scss', 'sql', 'ipynb'
]

MAX_CODE_LENGTH = 1000

def analyze_code(file_path, client):
    with open(file_path, 'r') as file:
        code_content = file.read()

    if len(code_content) > MAX_CODE_LENGTH:
        code_content = code_content[:MAX_CODE_LENGTH]

    while True:
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": f"""Here is a piece of code:
                        {code_content}
Answer the following questions:

1. Brief description: Write a brief description of what the code does (maximum 40 words).
2. Code evaluation: Give an overall rating of the code from 1 to 10, considering factors like clarity, efficiency, and best practices.
Answers:

1. Brief description:
2. Code evaluation:
                        """,
                    }
                ],
                model="llama3-8b-8192",
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            error_message = str(e)
            if "rate limit" in error_message:
                print(f" [!] Rate limit reached. Retrying in 10 seconds...")
                time.sleep(10)
            elif "context_length_exceeded" in error_message:
                print(f" [!] Message too long. Skipping file {file_path}")
                return "Error: Message too long to be processed."
            else:
                print(f" [!] Unexpected error: {e}")
                return f"Error: {e}"

def analyze_repository(repo_url, counter, lock):
    load_dotenv()
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    repo_name = repo_url.split('/')[-1].replace('.git', '')

    repo_path = os.path.join('../Repo', repo_name)

    if not os.path.exists(repo_path):
        try:
            os.makedirs(repo_path)
            print(f" [x] Created directory {repo_path}")
        except OSError as e:
            print(f" [!] Failed to create directory {repo_path}: {e}")
            return

        try:
            subprocess.run(['git', 'clone', repo_url, repo_path], check=True)
            print(f" [x] Cloned {repo_url} into {repo_path}")
        except subprocess.CalledProcessError as e:
            print(f" [!] Failed to clone {repo_url}: {e}")
            return
    else:
        print(f" [x] Repository directory {repo_path} already exists")

    valid_files = []
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.split('.')[-1] in VALID_EXTENSIONS:
                valid_files.append(os.path.join(root, file))

    if not valid_files:
        print(" [!] No files with valid extensions found. Stopping analysis.")
        return

    analysis_results = {}
    for file_path in valid_files:
        try:
            result = analyze_code(file_path, client)
            analysis_results[os.path.relpath(file_path, repo_path)] = result
            print(f" [x] Analyzed {file_path}")
        except Exception as e:
            print(f" [!] Failed to analyze {file_path}: {e}")

    analyzed_repo_path = os.path.join('../repo_analyzed', repo_name)
    if not os.path.exists(analyzed_repo_path):
        os.makedirs(analyzed_repo_path)
    
    json_path = os.path.join(analyzed_repo_path, 'analysis_results.json')
    with open(json_path, 'w') as json_file:
        json.dump(analysis_results, json_file, indent=4)
    print(f" [x] Saved analysis results to {json_path}")

    # Delete the repository directory after JSON file creation
    try:
        shutil.rmtree(repo_path)
        print(f" [x] Deleted repository directory {repo_path}")
    except OSError as e:
        print(f" [!] Error deleting repository directory {repo_path}: {e}")

    with lock:
        counter.value -= 1
        print(f" [x] Active processes: {counter.value}")

    analysis_results["name"]=repo_name
    r = requests.post('http://localhost:5001/analysis_results', json=analysis_results)
    if r.status_code == 200:
        try: 
            shutil.rmtree(analyzed_repo_path)
            print(f" [x] Deleted analyzed repository directory {analyzed_repo_path}")
        except OSError as e:
            print(f" [!] Error deleting analyzed repository directory {analyzed_repo_path}: {e}")

def keep_alive():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()
    while True:
        channel.basic_publish(exchange='', routing_key='keep_alive', body='keep_alive')
        time.sleep(30)

def worker_main(repo_url, counter, lock):
    with lock:
        counter.value += 1
        print(f" [x] Active processes: {counter.value}")
    analyze_repository(repo_url, counter, lock)

def main():
    load_dotenv()
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()

    channel.queue_declare(queue='Repositories')
    channel.queue_declare(queue='keep_alive')

    # Start keep-alive process
    keep_alive_process = multiprocessing.Process(target=keep_alive)
    keep_alive_process.daemon = True
    keep_alive_process.start()

    manager = Manager()
    counter = manager.Value('i', 0)  
    lock = manager.Lock()  

    def callback(ch, method, properties, body):
        repo_url = body.decode()
        print(f" [x] Received {repo_url}")
        process = multiprocessing.Process(target=worker_main, args=(repo_url, counter, lock))
        process.start()

    channel.basic_consume(queue='Repositories', on_message_callback=callback, auto_ack=True)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
