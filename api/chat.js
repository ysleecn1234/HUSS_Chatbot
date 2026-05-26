export const config = {
  runtime: 'edge',
};

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), { status: 405 });
  }

  const { model = 'gemini-2.5-flash', systemPrompt, contents } = await req.json();

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'Server configuration error: Missing API Key in environment variables.' }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  }

  try {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_instruction: { parts: [{ text: systemPrompt }] },
          contents: contents
        })
      }
    );

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      return new Response(JSON.stringify({ error: errData.error?.message || `HTTP ${response.status}` }), { status: response.status, headers: { 'Content-Type': 'application/json' } });
    }

    const data = await response.json();
    const replyText = data.candidates?.[0]?.content?.parts?.[0]?.text || '답변을 생성하지 못했어. 다시 물어봐!';
    return new Response(JSON.stringify({ reply: replyText }), { status: 200, headers: { 'Content-Type': 'application/json' } });

  } catch (error) {
    console.error('Gemini API Error:', error);
    return new Response(JSON.stringify({ error: 'Internal server error while communicating with AI provider.' }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  }
}
