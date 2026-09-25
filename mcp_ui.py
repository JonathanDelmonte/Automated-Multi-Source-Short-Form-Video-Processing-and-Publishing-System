"""MCP Apps surface: an embedded clip picker for UI-capable MCP clients.

The pipeline returns 3-15 clips per job; looking at them beats reading titles
out of JSON. Clients that support the MCP Apps extension (ChatGPT apps, mcp-ui
hosts, Claude) render the HTML below in a sandboxed iframe; every other client
ignores it and keeps working from the text/structured content exactly as
before.

(Neste fork o quadro so MOSTRA os cortes. A barra de publicar do upstream
chamava a ferramenta `publish_clip`, que saiu na Fase 0.3 com o Upload-Post:
o botao ficava na tela e o agente recebia "Unknown tool". Publicar e pela aba
Publicacao do painel. Um teste falha se o quadro voltar a chamar ferramenta que
o motor nao tem.)

One template, three data paths, because the ecosystem hasn't converged:
  1. Baked-in JSON — the per-call embedded resource appended to a successful
     list_clips result carries its data inline and renders with no bridge.
  2. window.openai.toolOutput — the ChatGPT Apps SDK injects the tool's
     structuredContent there; the tool's _meta names this template.
  3. postMessage handshake — MCP Apps / mcp-ui hosts that serve the template
     from resources/read and push render data after the iframe reports ready.

The iframe cannot fetch anything (host CSP), so the video previews use the
clips' absolute URLs and everything else is inline.
"""
import json

CLIP_PICKER_URI = "ui://virtu-clips/clip-picker"
MIME_TYPE = "text/html;profile=mcp-app"

RESOURCES = [
    {
        "uri": CLIP_PICKER_URI,
        "name": "clip-picker",
        "title": "Cortes do Virtu Clips",
        "description": (
            "Os cortes prontos de um projeto, cada um com a previa (9:16), o "
            "titulo e a duracao, sem sair da conversa."
        ),
        "mimeType": MIME_TYPE,
    },
]

# Kept as a plain string with a token instead of an f-string: the JS is full of
# braces and escaping them all is how bugs get in.
_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--paper:oklch(13% 0.014 265);--paper2:oklch(16.5% 0.015 265);
--ink:oklch(96% 0.006 262);--ink2:oklch(86% 0.01 262);--muted:oklch(64% 0.012 262);
--rule:oklch(96% 0.006 262 / .12)}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink2);
font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;font-size:14px;padding:12px}
h1{font-size:15px;font-weight:600;color:var(--ink);margin:0 0 10px}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
.card{background:var(--paper2);border:1px solid var(--rule);border-radius:10px;padding:8px}
.card video{width:100%;aspect-ratio:9/16;border-radius:6px;background:#000;display:block}
.card .t{margin-top:6px;font-size:12px;color:var(--ink);line-height:1.3;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .d{font-size:11px;color:var(--muted);margin-top:2px}
.empty{color:var(--muted)}
</style>
</head>
<body>
<h1 id="hd">Cortes do Virtu Clips</h1>
<div class="grid" id="grid"><span class="empty">Esperando os cortes…</span></div>
<script>
var inline = __OPENSHORTS_DATA__;

function render(data) {
  var clips = data.clips || [];
  document.getElementById('hd').textContent =
    clips.length + (clips.length === 1 ? ' corte' : ' cortes') +
    (data.job_id ? ' · projeto ' + data.job_id : '');
  var grid = document.getElementById('grid');
  grid.textContent = '';
  clips.forEach(function (clip) {
    var card = document.createElement('div');
    card.className = 'card';
    if (clip.video_url) {
      var v = document.createElement('video');
      v.src = clip.video_url;
      v.muted = true; v.controls = true; v.playsInline = true; v.preload = 'metadata';
      card.appendChild(v);
    }
    var t = document.createElement('div');
    t.className = 't';
    t.textContent = clip.title || ('Corte ' + (clip.index + 1));
    card.appendChild(t);
    var d = document.createElement('div');
    d.className = 'd';
    d.textContent = clip.duration_seconds ? clip.duration_seconds + ' s' : '';
    card.appendChild(d);
    grid.appendChild(card);
  });
}

// Data path 2: ChatGPT Apps SDK injects structuredContent here.
function fromOpenai() {
  var o = window.openai && (window.openai.toolOutput || window.openai.toolResponse);
  if (o && o.clips) { render(o); return true; }
  return false;
}

// Data path 3: MCP Apps / mcp-ui hosts push render data after we report ready.
window.addEventListener('message', function (ev) {
  var m = ev.data || {};
  var d = (m.payload && (m.payload.renderData || m.payload.toolOutput ||
           m.payload.structuredContent)) ||
          m.renderData || m.toolOutput || m.structuredContent;
  if (d && d.clips) render(d);
});
window.addEventListener('openai:set_globals', fromOpenai);

if (inline && inline.clips) { render(inline); }        // data path 1
else if (!fromOpenai()) {
  try { window.parent.postMessage({type: 'ui-lifecycle-iframe-ready'}, '*'); } catch (e) {}
}
</script>
</body>
</html>
"""


def clip_picker_html(data=None) -> str:
    """The picker HTML; ``data`` baked in when rendering a per-call resource.

    ``<`` is escaped in the JSON so a clip title can never close the script
    tag and inject markup.
    """
    payload = "null" if data is None else json.dumps(
        data, ensure_ascii=False).replace("<", "\\u003c")
    return _TEMPLATE.replace("__OPENSHORTS_DATA__", payload)
