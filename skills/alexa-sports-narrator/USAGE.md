# Sports Narrator — Guia de Uso / Usage Guide

Invocação / Invocation:
- **en-US:** "Alexa, open **sports narrator**"
- **pt-BR:** "Alexa, abrir **narrador esportivo**"

---

## Futebol / Soccer (Brasileirao Serie A)

| Portugues (pt-BR) | English (en-US) |
|---|---|
| "resultados do brasileirao" | "soccer scores" |
| "placar do futebol hoje" | "soccer scores today" |
| "quais foram os placares do futebol" | "what were the soccer scores" |
| "me diga os resultados do futebol" | "tell me the soccer results" |
| "jogos de hoje" | "football scores" |

---

## NFL

| Portugues (pt-BR) | English (en-US) |
|---|---|
| "placar da NFL" | "NFL scores" |
| "me diga os resultados da NFL" | "tell me the NFL results" |
| "quais foram os resultados da NFL hoje" | "what were the NFL scores today" |
| "jogos da NFL de ontem" | "what were the NFL games yesterday" |

---

## NBA

| Portugues (pt-BR) | English (en-US) |
|---|---|
| "placar da NBA" | "NBA scores" |
| "jogos da NBA hoje" | "NBA games today" |
| "quem ganhou na NBA" | "who won in the NBA" |
| "me diga os resultados da NBA" | "tell me the NBA results" |

---

## Salvar time favorito / Save favorite team

| Portugues (pt-BR) | English (en-US) |
|---|---|
| "meu time favorito é o Flamengo" | "my favorite team is Gremio" |
| "eu torço para o Corinthians" | "I follow the Chiefs" |
| "eu sou fã do Palmeiras" | "I am a Lakers fan" |
| "meu time é o Santos" | "my team is the Cowboys" |

**pt-BR:** aceita apenas os times listados abaixo (slot do tipo `SportTeam`).

**en-US:** aceita qualquer time — basta falar o nome (slot do tipo `AMAZON.SearchQuery`).

Times suportados em pt-BR / Teams supported in pt-BR:

- Futebol: Flamengo, Palmeiras, Corinthians, Sao Paulo, Santos, Gremio, Internacional, Atletico Mineiro, Cruzeiro, Botafogo, Vasco, Fluminense, Bahia, Fortaleza, Athletico Paranaense, Bragantino, Vitoria, Juventude, Ceara, Criciuma
- NFL: Kansas City Chiefs, Dallas Cowboys, New England Patriots
- NBA: Los Angeles Lakers, Golden State Warriors, Boston Celtics

---

## Atualizacao personalizada / Personalized update

Primeiro salve um time favorito. Depois:

| Portugues (pt-BR) | English (en-US) |
|---|---|
| "minha atualizacao personalizada" | "give me my sports update" |
| "como estao meus times" | "how are my teams doing" |
| "me atualize sobre meus times" | "update me on my teams" |
| "minhas noticias esportivas" | "my sports news" |

---

## Proximo jogo / Next game reminder

Requer um time favorito salvo. Alexa busca o proximo jogo e cria um lembrete 1 hora antes (necessita permissao de lembretes).

| Portugues (pt-BR) | English (en-US) |
|---|---|
| "quando é o próximo jogo do meu time" | "when does my team play next" |
| "quando meu time joga" | "when is my next game" |
| "qual o próximo jogo do meu time" | "what is my next game" |
| "me diga quando meu time joga" | "find my next game" |
| "me avise antes do jogo do meu time" | "alert me before my next match" |
| "próximo jogo do meu time" | "notify me before my next game" |

---

## Encerrar / Stop

| Portugues (pt-BR) | English (en-US) |
|---|---|
| "Alexa, parar" | "Alexa, stop" |
| "Alexa, cancelar" | "Alexa, cancel" |

---

## Notas

- O Brasileirao busca a season atual dinamicamente via API do Sportradar (competition `sr:competition:325`)
- Resultados de futebol retornam os ultimos 10 jogos com status `closed` ou `ended`
- A NFL retorna os ultimos 10 jogos com status `closed` ou `complete` (temporada atual calculada automaticamente)
- A NBA retorna os ultimos 10 jogos com status `closed` ou `complete`
- A atualizacao personalizada so busca dados dos esportes que o usuario acompanha
- Respostas em pt-BR quando o dispositivo esta configurado para Portuguese (Brazil)
- O dispositivo Alexa precisa estar configurado no idioma correto para reconhecer a invocacao ("sports narrator" em en-US, "narrador esportivo" em pt-BR)
