from google import genai

client = genai.Client(api_key="AIzaSyAVvA5ey7qLQBHrrLh2TI1ijv58TKNEKTw")

response = client.models.generate_content(
    model="gemini-2.0-flash", contents="Объясни как работает искусственный интеллект"
)

print(response.text)
