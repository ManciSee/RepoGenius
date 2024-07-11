import os
import json
import pika

def invia_repositories():
    # Leggi il file JSON
    directory = "../../repositories/"
    file_path = os.path.join(directory, "repositories.json")
    if not os.path.exists(file_path):
        print("Il file repositories.json non esiste. Esegui fetch_repositories.py prima di questo script.")
        return
    
    with open(file_path, 'r') as file:
        dati = json.load(file)
    
    repositories = dati['repositories']

    # Connessione a RabbitMQ
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    channel.queue_declare(queue='Repositories')

    # Invia le repository
    for repo in repositories:
        channel.basic_publish(exchange='', routing_key='Repositories', body=repo)
        print(f" [x] Sent '{repo}'")

    connection.close()

# Chiamata alla funzione per inviare le repository
invia_repositories()
