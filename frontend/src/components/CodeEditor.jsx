import { useRef, useState, useCallback } from "react";
import {
  Box,
  HStack,
  Button,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalCloseButton,
  ModalBody,
  Textarea,
  ModalFooter,
} from "@chakra-ui/react";
import { Editor, DiffEditor } from "@monaco-editor/react";
import Output from "./Output";
import "./Override.css";

function deleteLine(editorRef, lineno, isEnd, snapshots, onComplete) {
  const model = editorRef.current.getModel();

  if (lineno > model.getLineCount() || lineno < 1) {
    if (isEnd) {
      snapshots.current.push(editorRef.current.getModel().getValue());
    }
    onComplete();
    return;
  }

  const startColumn = 1;
  const endColumn = model.getLineMaxColumn(lineno);

  const lineText = model.getValueInRange(
    new monaco.Range(lineno, startColumn, lineno, endColumn)
  );
  const textArray = [...lineText];

  function deleteCharacter(index) {
    if (index < 0) {
      if (lineno < model.getLineCount()) {
        editorRef.current.executeEdits("", [
          {
            range: new monaco.Range(
              lineno,
              model.getLineMaxColumn(lineno),
              lineno + 1,
              1
            ),
            text: "",
            forceMoveMarkers: true,
          },
        ]);
      }
      onComplete();
      return;
    }

    const range = new monaco.Range(lineno, index + 1, lineno, index + 2);

    editorRef.current.executeEdits("", [
      { range: range, text: "", forceMoveMarkers: true },
    ]);

    setTimeout(() => deleteCharacter(index - 1), 2);
  }

  deleteCharacter(textArray.length - 1);
}

// Function to insert a single character
function insertCharacter(
  index,
  textArray,
  onComplete,
  editorRef,
  model,
  isEnd,
  snapshots
) {
  if (index >= textArray.length) {
    if (isEnd) {
      snapshots.current.push(editorRef.current.getModel().getValue());
    }
    onComplete();
    return;
  }

  const position = editorRef.current.getPosition();
  let range, newText, newPosition;

  if (textArray[index] === "\n") {
    range = new monaco.Range(
      position.lineNumber,
      model.getLineMaxColumn(position.lineNumber),
      position.lineNumber,
      model.getLineMaxColumn(position.lineNumber)
    );
    newText = "\n";
    newPosition = { lineNumber: position.lineNumber + 1, column: 1 };
  } else {
    range = new monaco.Range(
      position.lineNumber,
      position.column,
      position.lineNumber,
      position.column
    );
    newText = textArray[index];
    newPosition = {
      lineNumber: position.lineNumber,
      column: position.column + 1,
    };
  }

  editorRef.current.executeEdits("", [
    { range: range, text: newText, forceMoveMarkers: true },
  ]);

  editorRef.current.setPosition(newPosition);

  setTimeout(
    () =>
      insertCharacter(
        index + 1,
        textArray,
        onComplete,
        editorRef,
        model,
        isEnd,
        snapshots
      ),
    2
  );
}

function addLine(editorRef, lineno, text, isEnd, snapshots, onComplete) {
  const model = editorRef.current.getModel();
  const textArray = text.split("");

  // Initial setup to position cursor correctly before starting typing effect
  if (lineno <= model.getLineCount()) {
    editorRef.current.revealLine(lineno);
    // First shift rest of content down
    const rangeToInsertNewLine = new monaco.Range(lineno, 1, lineno, 1);
    editorRef.current.executeEdits("", [
      { range: rangeToInsertNewLine, text: "\n", forceMoveMarkers: true },
    ]);
    // Then set cursor to start of line
    editorRef.current.setPosition({ lineNumber: lineno, column: 1 });
  } else {
    // Append a newline to the end if adding beyond the last line
    const lastLine = model.getLineCount();
    const lastLineMaxColumn = model.getLineMaxColumn(lastLine);
    editorRef.current.setPosition({
      lineNumber: lastLine,
      column: lastLineMaxColumn,
    });
    editorRef.current.executeEdits("", [
      {
        range: new monaco.Range(
          lastLine,
          lastLineMaxColumn,
          lastLine,
          lastLineMaxColumn
        ),
        text: "\n",
        forceMoveMarkers: true,
      },
    ]);
  }

  insertCharacter(0, textArray, onComplete, editorRef, model, isEnd, snapshots); // Start inserting characters
}

const CodeEditor = () => {
  // Traceback (most recent call last):
  //   File "/Users/adrien/hndemo/backend/example.py", line 127, in <module>
  //     pay_for_day(emp_id, '2024-02-29')
  //   File "/Users/adrien/hndemo/backend/example.py", line 114, in pay_for_day
  //     if result.is_weekend:
  //        ^^^^^^^^^^^^^^^^^
  // AttributeError: 'NoneType' object has no attribute 'is_weekend'

  const [traceback, setTraceback] = useState("");

  const editorRef = useRef(null);
  const [editorReady, setEditorReady] = useState(false);
  const [prints, setPrints] = useState([]);
  const [step, setStep] = useState(null);
  const [codeStep, setCodeStep] = useState(0); // how far the editor has gotten, we use this to slow down the terminal output to match editor
  const [originalText, setOriginalText] = useState("");
  const [newText, setNewText] = useState("");
  const queueBlockedRef = useRef(false);
  const snapshots = useRef([]);
  const messagesRef = useRef([]);
  const processingRef = useRef(false);
  const [shouldCollectTraceback, setShouldCollectTraceback] = useState(true);

  const processQueue = useCallback(() => {
    if (
      processingRef.current ||
      messagesRef.current.length === 0 ||
      !editorReady ||
      queueBlockedRef.current
    )
      return;

    processingRef.current = true;
    const message = messagesRef.current.shift();
    const processNext = () => {
      processingRef.current = false;
      if (messagesRef.current.length > 0) {
        processQueue();
      }
    };

    if (message.step >= codeStep) {
      setCodeStep(message.step);
    }

    if (message.type === "i") {
      // todo: step stuff
      addLine(
        editorRef,
        message.lineno + 1,
        message.text,
        message.end,
        snapshots,
        processNext
      );
    } else if (message.type === "d") {
      deleteLine(
        editorRef,
        message.lineno + 1,
        message.end,
        snapshots,
        processNext
      );
    }
  });

  const onMount = (editor, monaco) => {
    editorRef.current = editor;
    setEditorReady(true);
    editor.focus();
  };

  const handleTracebackInput = () => {
    setPrints([
      {
        text: "Error we're trying to fix:",
        format: "",
        step: 0,
      },
      {
        text: traceback,
        format: "error",
        step: 0,
      },
    ]);
    setShouldCollectTraceback(false);
  };

  const renderOutput = () => {
    if (shouldCollectTraceback) {
      return (
        <Modal isOpen={true} onClose={() => setShouldCollectTraceback(false)}>
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>Stack Trace</ModalHeader>
            <ModalCloseButton />
            <ModalBody>
              <Textarea
                onChange={(e) => setTraceback(e.target.value)}
                style={{ minWidth: "100%", height: "50vh" }}
              />
            </ModalBody>
            <ModalFooter>
              <Button
                colorScheme="blue"
                mr={3}
                onClick={() => handleTracebackInput()}
              >
                Enter
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      );
    }
    return (
      <Output
        prints={prints}
        setPrints={setPrints}
        messagesRef={messagesRef}
        processQueue={processQueue}
        editorReady={editorReady}
        snapshots={snapshots}
        step={step}
        setStep={setStep}
        setOriginalText={setOriginalText}
        setNewText={setNewText}
        queueBlockedRef={queueBlockedRef}
        codeStep={codeStep}
        setCodeStep={setCodeStep}
        traceback={traceback}
      />
    );
  };

  return (
    <Box>
      <HStack spacing={4}>
        {renderOutput()}

        <Box w="50%">
          <div style={{ display: step === null ? "block" : "none" }}>
            <Editor
              options={{
                minimap: {
                  enabled: false,
                },
                wordWrap: "on",
                fontSize: 15,
              }}
              height="90vh"
              theme="vs-dark"
              language="python"
              defaultValue={""}
              onMount={onMount}
            />
          </div>
          <div style={{ display: step === null ? "none" : "block" }}>
            <DiffEditor
              height="90vh"
              theme="vs-dark"
              language="python"
              original={originalText || ""}
              modified={newText || ""}
              options={{
                renderSideBySide: false,
                readOnly: true,
                fontSize: 15,
              }}
            />
          </div>
        </Box>
      </HStack>
    </Box>
  );
};

export default CodeEditor;
