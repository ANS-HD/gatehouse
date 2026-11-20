import type { Provider } from "../providers/schemas";

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, "'\\''")}'`;
}

export function buildApiExamples(baseUrl: string, model: string, protocol: Provider["protocol"]) {
  const anthropic = protocol === "anthropic";
  const endpoint = `${baseUrl.replace(/\/+$/, "")}/${anthropic ? "messages" : "chat/completions"}`;
  const payload = {
    model,
    messages: [{ role: "user", content: "你好，请简单介绍一下自己。" }],
    max_tokens: 128,
  };
  const headers = anthropic
    ? [
        '  -H "x-api-key: $GATEHOUSE_API_KEY"',
        "  -H 'anthropic-version: 2023-06-01'",
      ]
    : ['  -H "Authorization: Bearer $GATEHOUSE_API_KEY"'];
  const curl = [
    `curl --request POST ${shellQuote(endpoint)}`,
    ...headers,
    "  -H 'Content-Type: application/json'",
    `  --data-raw ${shellQuote(JSON.stringify(payload, null, 2))}`,
  ].join(" \\\n");
  const pythonHeaders = anthropic
    ? '    "x-api-key": os.environ["GATEHOUSE_API_KEY"],\n    "anthropic-version": "2023-06-01",'
    : '    "Authorization": f"Bearer {os.environ[\'GATEHOUSE_API_KEY\']}",';
  const python = [
    "import json",
    "import os",
    "from urllib.request import Request, urlopen",
    "",
    `url = ${JSON.stringify(endpoint)}`,
    `payload = ${JSON.stringify(payload, null, 4)}`,
    "headers = {",
    pythonHeaders,
    '    "Content-Type": "application/json",',
    "}",
    "request = Request(",
    '    url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"',
    ")",
    "with urlopen(request, timeout=180) as response:",
    "    result = json.load(response)",
    'print(json.dumps(result, ensure_ascii=False, indent=2))',
  ].join("\n");

  return { endpoint, curl, python };
}
