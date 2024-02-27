import os
from urllib.parse import quote

import pylspclient
import subprocess
from pylspclient.lsp_structs import TextDocumentItem, LANGUAGE_IDENTIFIER, Position


class LspClientWrapper:
    DEFAULT_CAPABILITIES = {
        "textDocument": {
            "completion": {
                "completionItem": {
                    "commitCharactersSupport": True,
                    "documentationFormat": ["markdown", "plaintext"],
                    "snippetSupport": True,
                }
            }
        }
    }

    def __init__(self, root_path):
        self.default_path = root_path
        self.uri = self.to_uri(self.default_path)
        self.server = self.server_process()
        self.json_rpc = pylspclient.JsonRpcEndpoint(
            self.server.stdin, self.server.stdout
        )
        self.lsp_endpoint = pylspclient.LspEndpoint(self.json_rpc)
        self.lsp_client = pylspclient.LspClient(self.lsp_endpoint)
        self.initialization_options = None
        self.capabilities = self.DEFAULT_CAPABILITIES
        self.trace = "off"
        self.workspace_folders = None

    def server_process(self) -> subprocess.Popen:
        pylsp_cmd = ["pylsp", "--port", "4444"]
        p = subprocess.Popen(
            pylsp_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return p

    def to_uri(self, path: str) -> str:
        return f"file://{path}"

    def initialize(self):
        self.lsp_client.initialize(
            None,
            None,
            self.uri,
            self.initialization_options,
            self.capabilities,
            self.trace,
            self.workspace_folders,
        )
        self.lsp_client.initialized()

    def convert_to_uri(self, file_path: str) -> str:
        absolute_path = os.path.abspath(file_path)
        return "file://" + quote(absolute_path)

    def get_symbols(self, file_path: str) -> str:
        uri = self.convert_to_uri(file_path)
        document = TextDocumentItem(
            uri=uri, languageId=LANGUAGE_IDENTIFIER.PYTHON, version=0, text=""
        )
        result = self.lsp_client.documentSymbol(document)
        return result

    def get_document_symbol(self, file_path: str):
        uri = self.convert_to_uri(file_path)
        document = TextDocumentItem(
            uri=uri, languageId=LANGUAGE_IDENTIFIER.PYTHON, version=0, text=""
        )
        result = self.lsp_client.documentSymbol(document)
        return result

    def get_definition(self, file_path: str, position: Position):
        uri = self.convert_to_uri(file_path)
        document = TextDocumentItem(
            uri=uri, languageId=LANGUAGE_IDENTIFIER.PYTHON, version=0, text=""
        )
        return self.lsp_client.definition(document, position)

    def get_declaration(self, file_path: str, position: Position):
        uri = self.convert_to_uri(file_path)
        document = TextDocumentItem(
            uri=uri, languageId=LANGUAGE_IDENTIFIER.PYTHON, version=0, text=""
        )
        return self.lsp_client.declaration(document, position)

    def shutdown(self):
        self.lsp_client.shutdown()
