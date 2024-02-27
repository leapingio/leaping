import { useEffect } from "react";

function Socket({
  setPrints,
  messagesRef,
  processQueue,
  editorReady,
  setWs,
  setCodeStep,
}) {
  useEffect(() => {
    const socket = new WebSocket("ws://localhost:8000/ws");
    setWs(socket);

    socket.addEventListener("message", function (event) {
      const message = JSON.parse(event.data);

      if (message.type === "p") {
        setPrints((prev) => [
          ...prev,
          { text: message.text, format: message.format, step: message.step },
        ]);
        setCodeStep(message.step);
      } else {
        messagesRef.current.push(message);
        processQueue();
      }
    });

    return () => {
      socket.close();
    };
  }, [editorReady]);

  return null;
}

export default Socket;
