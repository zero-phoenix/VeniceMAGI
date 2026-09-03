/**
 * Tarjeta de intervención de un agente (Plan MAGI 9.0 §7.1).
 *
 * Estaba definida DENTRO de App.tsx, que es el ejemplo que el plan usa para
 * explicar por qué había que descomponerlo: un componente anidado en el
 * fichero de 903 líneas no se puede probar por separado, no se puede
 * reutilizar, y obliga a leer entera la pantalla principal para tocarlo.
 */
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const AgentMessageCard = ({ msg, telemetry, renderCode }: any) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  let body = "";
  let conclusion = "";

  const cleanText = (str: string) => {
    return str
      .replace(/^(?:###\s*)?\*\*?CONCLUSIÓ[NN](?:\s*FINAL\s*CONSOLIDADA)?:?\*\*?\s*/gi, '')
      .replace(/^\*\*?CONCLUSIÓ[NN]:?\*\*?\s*/gi, '')
      .trim();
  };

  if (msg.agent === 'USER') {
    body = msg.content || "";
  } else {
    let rawContent = (msg.content || "").trim();
    rawContent = cleanText(rawContent);

    const paragraphs = rawContent.split(/\n\s*\n/);
    if (paragraphs.length > 1) {
      conclusion = cleanText(paragraphs[paragraphs.length - 1]);
      body = cleanText(paragraphs.slice(0, paragraphs.length - 1).join('\n\n'));
    } else {
      conclusion = rawContent;
      body = "";
    }
  }

  return (
    <div className="msg-card" data-rol={msg.agent}>
      <div className="card-header">
        <div className="card-quien">
          {/* La barra de color la pinta el CSS desde `data-rol`. Antes se
              decidía aquí con un ternario de cuatro ramas que apuntaba a
              `--var` y `--fn`, dos variables que no existen en ninguna hoja:
              el nombre del nodo salía sin color y nadie lo había notado. */}
          <strong className="card-agente">{msg.agent}</strong>
          <span className="card-papel">{msg.role}</span>
        </div>
        <div className="card-meta">
          <span className="mono">{msg.provider}</span>
          {telemetry?.find((t: any) => t.provider === msg.provider) && (
            <span className="mono card-latencia">
              {telemetry.find((t: any) => t.provider === msg.provider).avg_latency_ms.toFixed(0)} ms
            </span>
          )}
        </div>
      </div>
      <div className="card-body">
        {msg.agent === 'USER' ? (
          <div>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: renderCode }}>
              {msg.content}
            </ReactMarkdown>
          </div>
        ) : (
          <>
            {conclusion && (
              <div className="card-conclusion-text">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: renderCode }}>
                  {conclusion}
                </ReactMarkdown>
              </div>
            )}

            {body && (
              <div style={{ marginTop: '8px' }}>
                <button className="card-mas"
                  onClick={() => setIsExpanded(!isExpanded)}>
                  {isExpanded ? 'Ocultar análisis ▴' : 'Ver análisis completo ▾'}
                </button>
                {isExpanded && (
                  <div className="card-body-text">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: renderCode }}>
                      {body}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default AgentMessageCard;
