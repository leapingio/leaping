import argparse
from socket import socket, AF_INET, SOCK_STREAM
import threading
import time
from prompt_toolkit import prompt

global stop_spinner
stop_spinner = threading.Event()
def spinner_animation(message="Loading..."):
    spinner_chars = ['|', '/', '-', '\\']
    idx = 0
    while not stop_spinner.is_set():
        print(f"\r{message} {spinner_chars[idx % len(spinner_chars)]}", end='')
        idx += 1
        time.sleep(0.1)
    print('\r', end='')

def create_spinner():
    global stop_spinner
    stop_spinner.clear()
    spinner_thread = threading.Thread(target=spinner_animation, args=("Thinking...",))
    spinner_thread.start()
    return spinner_thread

def stop_spinner_animation(spinner_thread):
    stop_spinner.set()
    spinner_thread.join()




def main():
    parser = argparse.ArgumentParser(description="W")
    parser.add_argument('-p', '--port', type=int, help='The temporary file generated by pytest-leaping', required=True)

    args = parser.parse_args()
    if not args.port:
        raise ValueError("Port number not provided. Exiting...")

    global stop_spinner

    print(""" 
 _                     _             
| |    ___  __ _ _ __ (_)_ __   __ _ 
| |   / _ \\/ _` | '_ \\| | '_ \\ / _` |
| |__|  __/ (_| | |_) | | | | | (_| |
|_____\\___|\\__,_| .__/|_|_| |_|\\__, |
                |_|            |___/ 
""")

    sock = socket(AF_INET, SOCK_STREAM)
    sock.connect(('localhost', args.port))

    spinner = create_spinner()
    stop_sent = False
    while not stop_sent:
        response = sock.recv(2048)
        stop_spinner_animation(spinner)
        if response == b"LEAPING_STOP":
            break
        print(response.decode("utf-8"), end="")


    while True:
        user_input = prompt("\nIf the explanation is wrong, say why and we'll try again. Press q to exit: \n> ")

        if user_input.strip() == "q" or user_input.strip() == "exit":
            sock.sendall(b"exit")
            break
        elif user_input.strip() == "":  # Check if the input is just an Enter key press (empty string)
            continue  # Skip the rest of the loop and prompt again
        sock.sendall(user_input.encode("utf-8"))
        spinner = create_spinner()
        stop_sent = False
        while not stop_sent:
            response = sock.recv(2048)
            stop_spinner_animation(spinner)
            if response == b"LEAPING_STOP":
                break
            print(response.decode("utf-8"), end="")
