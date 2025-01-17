from flask import Flask, render_template, request, jsonify, abort
import requests
import os
import json
import pika
import re
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app)

def trova_repositories(linguaggio, risultati_per_pagina, pagine,topic):
    repositories = []
    for pagina in range(1, pagine + 1):
        url = f"https://api.github.com/search/repositories?q=language:{linguaggio}+topic:{topic}&sort=stars&per_page={str(risultati_per_pagina)}&page={str(pagina)}"
        risposta = requests.get(url)
        if risposta.status_code == 200:
            dati = risposta.json()
            repositories.extend(dati['items'])
        else:
            print(f"Errore: {risposta.status_code}")
            return []
    return repositories

def trova_repositoriesfixed(linguaggio='', risultati_per_pagina='', pagine='', topic=''):
    repositories = []
    
    # Check if pagine is provided and is a valid integer
    if pagine:
        try:
            pagine = int(pagine)
        except ValueError:
            print("Errore: 'pagine' deve essere un numero intero.")
            return []
    else:
        pagine = 1  # Default to 1 if not provided or empty

    # Loop through each page
    for pagina in range(1, pagine + 1):
        query_parts = []
        
        # Include parameters if they are not empty strings
        if linguaggio:
            query_parts.append(f"language:{linguaggio}")
        if topic:
            query_parts.append(f"topic:{topic}")
        
        query = '+'.join(query_parts)
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars"
        
        # Add per_page parameter if it is not an empty string
        if risultati_per_pagina:
            url += f"&per_page={risultati_per_pagina}"
        
        # Add page parameter to the URL
        url += f"&page={pagina}"
        
        # Make the request
        risposta = requests.get(url)
        if risposta.status_code == 200:
            dati = risposta.json()
            repositories.extend(dati['items'])
        else:
            print(f"Errore: {risposta.status_code}")
            return []
    
    return repositories

def crea_file_repository(repositories):
    directory = "repositories"
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    file_path = os.path.join(directory, "repositories.json")
    """ This code append the link in the file repositories.json """
    # if os.path.exists(file_path):
    #     with open(file_path, 'r') as file:
    #         try:
    #             dati_esistenti = json.load(file)
    #             link_repository_list = dati_esistenti.get("repositories", [])
    #         except json.JSONDecodeError:
    #             link_repository_list = []
    # else:
    #     link_repository_list = []

    # for repo in repositories:
    #     link_repository_list.append(repo['html_url'])

    # with open(file_path, 'w') as file:
    #     json.dump({"repositories": link_repository_list}, file, indent=4)
    
    link_repository_list = [repo['html_url'] for repo in repositories]
    with open(file_path, 'w') as file:
        json.dump({"repositories": link_repository_list}, file, indent=4)

def aggiungi_repository(link):
    directory = "repositories"
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    file_path = os.path.join(directory, "repositories.json")
    """ This code append the link in the file repositories.json """
    # if os.path.exists(file_path):
    #     with open(file_path, 'r') as file:
    #         try:
    #             dati_esistenti = json.load(file)
    #             link_repository_list = dati_esistenti.get("repositories", [])
    #         except json.JSONDecodeError:
    #             link_repository_list = []
    # else:
    #     link_repository_list = []

    # link_repository_list.append(link)

    # with open(file_path, 'w') as file:
    #     json.dump({"repositories": link_repository_list}, file, indent=4)

    link_repository_list = [link]
    with open(file_path, 'w') as file:
        json.dump({"repositories": link_repository_list}, file, indent=4)

def invia_repositories():
    directory = "repositories"
    file_path = os.path.join(directory, "repositories.json")
    if not os.path.exists(file_path):
        print("Il file repositories.json non esiste.")
        return {"status": "error", "message": "Il file repositories.json non esiste."}

    if os.path.getsize(file_path) == 0:
        print("Il file repositories.json è vuoto.")
        return {"status": "error", "message": "Il file repositories.json è vuoto."}

    with open(file_path, 'r') as file:
        try:
            dati = json.load(file)
        except json.JSONDecodeError:
            print("Errore nel decodificare il file JSON.")
            return {"status": "error", "message": "Errore nel decodificare il file JSON."}

    repositories = dati['repositories']

    connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ['RABBITMQ_HOST']))
    channel = connection.channel()

    channel.queue_declare(queue='Repositories')

    for repo in repositories:
        channel.basic_publish(exchange='', routing_key='Repositories', body=repo)
        print(f" [x] Sent '{repo}'")

    connection.close()
    return {"status": "success", "message": "Repositories inviate con successo a RabbitMQ"}

def is_valid_github_link(link):
    github_repo_pattern = r"^https:\/\/github\.com\/([^\/]+)\/([^\/]+)\/?$"
    match = re.match(github_repo_pattern, link)
    return match

def check_github_repo_exists(link):
    normalized_link = link.rstrip('/')
    api_url = f"https://api.github.com/repos/{normalized_link.replace('https://github.com/', '')}"
    response = requests.get(api_url)
    return response.status_code == 200

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search", methods=["POST"])
def search():
    data = request.json
    linguaggio = data.get("linguaggio")
    topic = data.get("topic")
    risultati_per_pagina = int(data.get("risultati_per_pagina", 10))
    pagine = int(data.get("pagine", 1))
    
    repositories = trova_repositoriesfixed(linguaggio, risultati_per_pagina, pagine,topic)
    if repositories:
        crea_file_repository(repositories)
        return jsonify({"status": "success", "repositories": [repo['html_url'] for repo in repositories]})
    else:
        return jsonify({"status": "error", "message": "Errore nella ricerca dei repository"}), 500

@app.route("/searchlink", methods=["POST"])
def searchlink():
    data = request.json
    link = data.get("link")

    if not link:
        return jsonify({"status": "error", "message": "Nessun link fornito."}), 400

    if not is_valid_github_link(link):
        return jsonify({"status": "error", "message": "Il link fornito non è un link valido di GitHub."}), 400

    if not check_github_repo_exists(link):
        return jsonify({"status": "error", "message": "Il repository non esiste su GitHub."}), 400

    aggiungi_repository(link.rstrip('/'))
    return jsonify({"status": "success", "message": "Repository aggiunto con successo.", "repository": link})

@app.route("/send", methods=["POST"])
def send():
    result = invia_repositories()
    if result["status"] == "success":
        return jsonify(result)
    else:
        return jsonify(result), 500

@app.route('/analysis_results', methods=['POST'])
def analysis_results():
    event_data = request.json
    #print(event_data)
    
    socketio.emit('new_analysis_result', event_data)
    name = event_data.get('name', 'default_name')  
    directory = "analyzed_repositories"
    if not os.path.exists(directory):
        os.makedirs(directory)
    file_name = os.path.join(directory, f"{name}.json")
    with open(file_name, 'w') as file:
        json.dump(event_data, file, indent=4)
    return jsonify({"status": "success", "results": event_data})

@app.route('/getData/<filename>')
def get_data(filename):
    directory = "analyzed_repositories"
    file_path = os.path.join(directory, f'{filename}.json')
    if not os.path.exists(file_path):
        abort(404)
    with open(file_path, 'r') as json_file:
        data = json.load(json_file)
    return render_template('display.html', data=data)

@socketio.on('connect')
def handle_connect():
    print("Client connected")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
