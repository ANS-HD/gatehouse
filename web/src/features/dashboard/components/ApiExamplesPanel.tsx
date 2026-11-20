import { useState } from "react";
import { CodeOutlined, CopyOutlined } from "@ant-design/icons";
import { Button, Card, Select, Space, Tabs, Tag, Typography } from "antd";
import type { Provider } from "../../providers/schemas";
import { buildApiExamples } from "../api-examples";
import type { GatewayKey } from "../schemas";

const { Paragraph, Text } = Typography;

type Props = {
  baseUrl: string;
  keys: GatewayKey[];
  providers: Provider[];
  onCopy: (value: string) => void;
};

export function ApiExamplesPanel({ baseUrl, keys, providers, onCopy }: Props) {
  const [selectedKeyId, setSelectedKeyId] = useState<string>();
  const [language, setLanguage] = useState("curl");
  const availableKeys = keys.filter((key) => key.enabled && key.model_name && providers.some(
    (provider) => provider.id === key.provider_id && provider.enabled
      && provider.models.some((model) => model.id === key.model_id),
  ));
  const selectedKey = availableKeys.find((key) => key.id === selectedKeyId) ?? availableKeys[0];
  const provider = providers.find((item) => item.id === selectedKey?.provider_id);
  const protocol = provider?.protocol ?? "openai";
  const examples = buildApiExamples(
    baseUrl,
    selectedKey?.model_name ?? "替换为密钥绑定的模型",
    protocol,
  );
  const snippet = language === "python" ? examples.python : examples.curl;

  return (
    <Card
      variant="borderless"
      className="panel-card api-examples-card"
      title={<Space><CodeOutlined />调用示例</Space>}
      extra={<Button icon={<CopyOutlined />} onClick={() => onCopy(snippet)}>复制示例</Button>}
    >
      <Paragraph type="secondary">
        {selectedKey
          ? "选择一枚已启用的密钥，示例会自动使用它绑定的模型。"
          : "先创建一枚访问密钥并保存完整密钥，示例会自动匹配其模型。"}
      </Paragraph>
      <div className="api-example-selector">
        <label htmlFor="api-example-key">调用密钥</label>
        <Select
          id="api-example-key"
          aria-label="调用密钥"
          value={selectedKey?.id}
          onChange={setSelectedKeyId}
          disabled={!availableKeys.length}
          placeholder="请先创建并启用访问密钥"
          options={availableKeys.map((key) => ({
            value: key.id,
            label: `${key.name} · ${key.provider_name} · ${key.model_name}`,
          }))}
        />
        <Tag color="cyan">{protocol === "anthropic" ? "Anthropic Messages" : "Chat Completions"}</Tag>
      </div>
      <div className="api-example-key-note">
        <Text>先在终端设置完整网关密钥：</Text>
        <Text code copyable>export GATEHOUSE_API_KEY='gw_替换为你保存的完整密钥'</Text>
        <Text type="secondary">完整密钥仅在创建时显示，列表中的省略前缀无法用于调用。请求中的 model 必须与密钥绑定的模型一致。</Text>
      </div>
      <Tabs
        activeKey={language}
        onChange={setLanguage}
        items={[
          { key: "curl", label: "cURL", children: <pre className="api-example-code"><code>{examples.curl}</code></pre> },
          { key: "python", label: "Python（标准库）", children: <pre className="api-example-code"><code>{examples.python}</code></pre> },
        ]}
      />
      <Text type="secondary">运行示例后会返回模型回复，调用记录可在下方「最近请求」中查看。</Text>
    </Card>
  );
}
