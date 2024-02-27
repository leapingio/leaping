import {
  Box,
  Text,
  VStack,
  HStack,
  Flex,
  Button,
  Textarea,
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverArrow,
  PopoverCloseButton,
  PopoverBody,
  PopoverFooter,
  Divider,
} from "@chakra-ui/react";
import React, { useEffect, useState } from "react";

function Prints({
  prints,
  snapshots,
  step,
  setStep,
  setOriginalText,
  setNewText,
  codeStep,
  setCodeStep,
  socket,
  queueBlockedRef,
  processQueue,
  traceback,
}) {
  useEffect(() => {
    const stepInt = parseInt(step); // why do we have to do this?
    setOriginalText(stepInt === 0 ? "" : snapshots.current[stepInt - 1]);
    setNewText(snapshots.current[stepInt]);
  }, [step]);

  const [context, setContext] = useState("");
  const [buttonExecution, setButtonExecution] = useState(0);

  function getPrintStyle(format) {
    const styles = {
      error: { color: "red" },
    };

    return styles[format] || {};
  }

  const groupedPrints = {};
  const fromGPT = {};
  const toGPT = {};

  for (const print of prints) {
    if (print.format === "from_gpt") {
      fromGPT[print.step] = print.text;
      continue;
    }
    if (print.format === "to_gpt") {
      toGPT[print.step] = print.text;
      continue;
    }

    if (!groupedPrints.hasOwnProperty(print.step)) {
      groupedPrints[print.step] = [];
    }

    const isFormatExist = groupedPrints[print.step].some(
      (existingPrint) => existingPrint.format === print.format
    );

    if (!isFormatExist) {
      groupedPrints[print.step].push(print);
    }
  }

  function run() {
    const runServer = () => {
      fetch("http://127.0.0.1:8000/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ traceback: traceback }),
      });
    };

    const pauseServer = () => {
      queueBlockedRef.current = true;
      socket.send(JSON.stringify({ type: "pause" }));
    };

    const resumeServer = () => {
      setCodeStep();
      queueBlockedRef.current = false;
      processQueue();
      socket.send(JSON.stringify({ type: "resume" }));
    };

    setButtonExecution(buttonExecution + 1);
    const buttonText = getButtonText();
    switch (buttonText) {
      case "Run":
        runServer();
        break;
      case "Pause":
        pauseServer();
        break;
      case "Resume":
        resumeServer();
        break;
      default:
        break;
    }
  }

  const getButtonText = () => {
    if (buttonExecution === 0) {
      return "Run";
    } else if (buttonExecution % 2 === 1) {
      return "Pause";
    }
    return "Resume";
  };

  const steps = Object.keys(groupedPrints)
    .map(Number)
    .filter((step) => step <= codeStep + 1)
    .sort((a, b) => a - b);

  const addMoreContext = () => {
    socket.send(
      JSON.stringify({
        type: "context",
        step: step,
        additionalContext: context,
      })
    );
  };

  return (
    <div style={{ maxHeight: "100vh", overflowY: "auto" }}>
      <Box bg="gray.800" borderRadius="md" height="90vh" position="relative">
        <Button variant="outline" colorScheme="green" m={4} onClick={run}>
          {getButtonText()}
        </Button>
        <Divider mb={"20px"} borderColor={"white"} />
        {steps
          .slice()
          .reverse()
          .map((step) => (
            <VStack
              key={step}
              spacing={1}
              align="left"
              overflowY="auto"
              style={{ maxHeight: "80%" }}
            >
              <Popover onClose={() => setStep(null)}>
                <PopoverTrigger>
                  <Box
                    border="1px"
                    borderColor="yellow.100"
                    borderRadius="md"
                    display="flex"
                    flex="1"
                    margin={"7px"}
                    p={2}
                    _hover={{
                      background: "blue.800",
                      cursor: "pointer",
                    }}
                    onClick={() => setStep(step)}
                  >
                    <VStack align="left">
                      {groupedPrints[step].map((print, index) => (
                        <Text
                          key={index}
                          fontFamily="monospace"
                          color="white"
                          {...getPrintStyle(print.format)}
                        >
                          {print.text.split("\n").map((line, index) => (
                            <React.Fragment key={index}>
                              {line}
                              <br />
                            </React.Fragment>
                          ))}
                        </Text>
                      ))}
                    </VStack>
                  </Box>
                </PopoverTrigger>
                <PopoverContent
                  color="white"
                  width="100%"
                  minWidth="400px"
                  maxWidth="750px"
                  height="400px"
                  maxHeight="90vh"
                  sx={{
                    overflow: "auto",
                  }}
                >
                  <PopoverCloseButton />
                  <PopoverBody flex="65%">
                    <Text fontWeight="bold" mb={4}>
                      To GPT:
                    </Text>
                    <Text>{toGPT[step] ? toGPT[step] : "No message"}</Text>
                  </PopoverBody>

                  <PopoverBody flex="65%">
                    <Text fontWeight="bold" mb={4}>
                      From GPT:
                    </Text>
                    <Text>{fromGPT[step] ? fromGPT[step] : "No message"}</Text>
                  </PopoverBody>

                  <PopoverFooter display="flex" justifyContent="space-between">
                    <Box flex="1">
                      <Flex alignItems="center">
                        <Textarea
                          width="100%"
                          placeholder="Add context..."
                          borderRadius="md"
                          resize="none"
                          onChange={(e) => setContext(e.target.value)}
                        />
                        <Button
                          ml={2}
                          onClick={addMoreContext}
                          colorScheme="blue"
                          borderRadius="md"
                        >
                          Send
                        </Button>
                      </Flex>
                    </Box>
                  </PopoverFooter>
                </PopoverContent>
              </Popover>
            </VStack>
          ))}
      </Box>
    </div>
  );
}

export default Prints;
