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
    // Inject system prompt into the first message to support older models like gemini-pro
    if (contents.length > 0 && contents[0].role === 'user') {
      contents[0].parts[0].text = `[System Instructions]\n${systemPrompt}\n\n[User Request]\n${contents[0].parts[0].text}`;
    }

    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent?alt=sse&key=${apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: contents
        })
      }
    );

    if (!response.ok) {
      const errText = await response.text();
      return new Response(JSON.stringify({ error: `API Error: ${response.status} - ${errText}` }), { status: response.status, headers: { 'Content-Type': 'application/json' } });
    }

    return new Response(response.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });

  } catch (error) {
    console.error('Gemini API Error:', error);
    return new Response(JSON.stringify({ error: 'Internal server error while communicating with AI provider.' }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  }
}
