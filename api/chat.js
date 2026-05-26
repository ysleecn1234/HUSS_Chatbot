export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { model = 'gemini-2.5-flash', systemPrompt, contents } = req.body;

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'Server configuration error: Missing API Key in environment variables.' });
  }

  try {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_instruction: { parts: [{ text: systemPrompt }] },
          contents: contents,
          generationConfig: {
            temperature: 0.7,
            maxOutputTokens: 4096,
            topP: 0.9
          }
        })
      }
    );

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      return res.status(response.status).json({ error: errData.error?.message || `HTTP ${response.status}` });
    }

    const data = await response.json();
    const replyText = data.candidates?.[0]?.content?.parts?.[0]?.text || '답변을 생성하지 못했어. 다시 물어봐!';
    return res.status(200).json({ reply: replyText });

  } catch (error) {
    console.error('Gemini API Error:', error);
    return res.status(500).json({ error: 'Internal server error while communicating with AI provider.' });
  }
}
