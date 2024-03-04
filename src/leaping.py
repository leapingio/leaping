import argparse
from socket import socket

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
import pyfiglet
import pickle
import socket

import typer



def main():
    parser = argparse.ArgumentParser(description="W")
    parser.add_argument('-p', '--port', type=str, help='The temporary file generated by pytest-leaping', required=True)

    args = parser.parse_args()
    print(args)
    if not args.port:
        raise ValueError("Port number not provided. Exiting...")
    #
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', int(args.port)))


    commands_completer = WordCompleter(['exit', 'hello', 'help'], ignore_case=True)
    ascii_art = pyfiglet.figlet_format("Leaping")
    print(ascii_art)
    print("Available commands: deeper, exit, fix, history")

    while True:
        user_input = prompt("Please enter a command: ", completer=commands_completer)
        print(user_input)
        if user_input.lower() == 'exit':
            sock.sendall(b'exit')
            print("Exiting...")
            break
        elif user_input.lower() == 'hello':
            sock.sendall(b'hello')
            print("Hello there!")
        elif user_input.lower() == 'help':
            print(
                "Available commands: exit, hello, help")  # figure out a nice way to find all the available commands at a point in time
        else:
            print("Unknown command. Type 'help' for a list of commands.")