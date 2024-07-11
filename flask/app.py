from flask import Flask, render_template, request, jsonify
import requests
import os
import json
import pika

app = Flask(__name__)

def trova_repositories(linguaggio, risultati_per_pagina, pagine):
    repositories = []
    for pagina in range(1, pagine + 1):
        url = f"https://api.github.com/search/repositories?q=language:{linguaggio}&sort=stars&per_page={str(risultati_per_pagina)}&page={str(pagina)}"
        risposta = requests.get(url)
        if risposta.status_code == 200:
            dati = risposta.json()
            repositories.extend(dati['items'])
        else:
            print(f"Errore: {risposta.status_code}")
            return []
    return repositories

def crea_file_repository(repositories):
    link_repository_list = []
    for repo in repositories:
        link_repository_list.append(repo['html_url'])
    
    directory = "repositories"
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    file_path = os.path.join(directory, "repositories.json")
    with open(file_path, 'w') as file:
        json.dump({"repositories": link_repository_list}, file, indent=4)

def invia_repositories():
    directory = "repositories"
    file_path = os.path.join(directory, "repositories.json")
    if not os.path.exists(file_path):
        print("Il file repositories.json non esiste.")
        return {"status": "error", "message": "Il file repositories.json non esiste."}

    with open(file_path, 'r') as file:
        dati = json.load(file)

    repositories = dati['repositories']

    # Usa 'rabbitmq' come hostname per RabbitMQ in Docker Compose
    connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ['RABBITMQ_HOST']))
    channel = connection.channel()

    channel.queue_declare(queue='Repositories')

    for repo in repositories:
        channel.basic_publish(exchange='', routing_key='Repositories', body=repo)
        print(f" [x] Sent '{repo}'")

    connection.close()
    return {"status": "success", "message": "Repositories inviate con successo a RabbitMQ"}


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search", methods=["POST"])
def search():
    data = request.json
    linguaggio = data.get("linguaggio")
    risultati_per_pagina = int(data.get("risultati_per_pagina", 10))
    pagine = int(data.get("pagine", 1))
    
    repositories = trova_repositories(linguaggio, risultati_per_pagina, pagine)
    if repositories:
        crea_file_repository(repositories)
        return jsonify({"status": "success", "repositories": [repo['html_url'] for repo in repositories]})
    else:
        return jsonify({"status": "error", "message": "Errore nella ricerca dei repository"}), 500

@app.route("/send", methods=["POST"])
def send():
    result = invia_repositories()
    if result["status"] == "success":
        return jsonify(result)
    else:
        return jsonify(result), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
