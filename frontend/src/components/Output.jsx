import { Box, Button } from "@chakra-ui/react";
import Socket from "./Socket";
import Prints from "./Prints";
import { useState } from "react";

const Output = ({
  prints,
  setPrints,
  messagesRef,
  processQueue,
  editorReady,
  snapshots,
  step,
  setStep,
  setOriginalText,
  setNewText,
  queueBlockedRef,
  codeStep,
  setCodeStep,
  traceback,
}) => {
  const [ws, setWs] = useState(null);

  return (
    <Box w="50%">
      <Prints
        prints={prints}
        snapshots={snapshots}
        step={step}
        setStep={setStep}
        setOriginalText={setOriginalText}
        setNewText={setNewText}
        codeStep={codeStep}
        setCodeStep={setCodeStep}
        socket={ws}
        queueBlockedRef={queueBlockedRef}
        processQueue={processQueue}
        traceback={traceback}
      />
      <Socket
        setPrints={setPrints}
        messagesRef={messagesRef}
        processQueue={processQueue}
        editorReady={editorReady}
        setWs={setWs}
        setCodeStep={setCodeStep}
      />
    </Box>
  );
};
export default Output;
