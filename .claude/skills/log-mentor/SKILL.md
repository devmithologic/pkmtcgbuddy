---
name: log-mentor
description: Writes a learning-log entry into `log_mentor/` documenting a code change and the concepts behind it — reference-style, concise, with links to official docs. Use this right after writing or modifying code that introduces a concept the developer hasn't met yet in this repo (a new FastAPI dependency, a Mongo aggregation stage, a React hook, a CORS setting, an async pattern, a Pydantic validator). Also use whenever the user says "document this", "log this change", "explain what we just built", "add this to the log", or asks for study notes on something just implemented. Default to using it after a vertical slice lands, even if nobody asked — the point of this repo is learning, and an undocumented concept is a lost lesson.
---

# Log Mentor

Este skill **no escribe la documentación**. Despacha al subagente `log-mentor`, que corre con Haiku y
tiene las instrucciones completas —cuándo merece entrada, el formato de nombres, la voz, la
plantilla— en `.claude/agents/log-mentor.md`.

## Qué hacer

Llama a la herramienta Agent:

```
Agent(
  subagent_type: "log-mentor",
  description: "Documentar <concepto>",
  prompt: "<el encargo, ver abajo>"
)
```

## Reglas

**No escribas tú la entrada.** Sabes hacerlo, y por eso hay que decirlo: el trabajo va al subagente
para no gastar el contexto de la sesión de trabajo en 150 líneas de prosa, y para no usar el modelo
más caro en una tarea que es redacción sobre una plantilla fija. Si te pones a escribirla, el cambio
no sirve de nada.

**Dale el alcance en el prompt, no el contenido.** El agente averigua por su cuenta qué cambió —lee
el diff, `CLAUDE.md` y los comentarios del código— así que no le resumas el cambio. Lo que sí necesita
es saber *dónde mirar*, porque un `git diff` grande puede mezclar varios trabajos:

- qué se acaba de tocar («los cambios sin confirmar en `backend/app/db/folder_repository.py` y
  `frontend/src/components/DeckList.jsx`»), o
- el rango de commits, si el trabajo ya está confirmado («desde `454f001`»).

Si de verdad hubo algo que no está ni en el diff ni en `CLAUDE.md` —una alternativa que se probó y se
descartó, una medición que se hizo y no se anotó— eso sí menciónalo: es lo único que el agente no
puede recuperar solo.

**Corre en segundo plano.** No lo esperes, no sigas preguntándole y **no te inventes su resultado**:
el aviso de que terminó llega solo. Cuando llegue, di qué ficheros creó, una línea por fichero. Si
decidió que nada merecía entrada, eso también se cuenta — es un resultado válido y a menudo el
correcto.

**Uno solo para todas las entradas.** Aunque el slice haya introducido tres conceptos, va un único
agente: la plantilla enlaza entradas hermanas en «Related concepts», y quien escribe las tres sabe qué
dicen las otras dos. Además los índices `15`, `16`, `17` se reparten sin colisionar, cosa que tres
agentes en paralelo no pueden garantizar.
