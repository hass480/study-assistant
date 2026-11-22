# Phase 11 Notes

## Setup fixes

The venv was made with uv, so it has no pip. Install packages with `uv pip install ...` so they land in the venv.

Terminals read ~/.bashrc only at startup. After changing it, run `source ~/.bashrc` or open a new terminal. VS Code's Run button and Code Runner use the environment from when VS Code launched, so run scripts from the terminal.

New terminals start in the home folder, so run `ae` then `ap` first.

The installed anthropic SDK does not accept `temperature`, so run tests several times instead of relying on temperature 0.

## Lesson 01: Prompt Engineering

Anatomy of a call: an API call has three parts. The system message holds rules that persist for the whole conversation. The user message is this turn's task. Prefill (optional) starts the model's reply. Rules for the whole conversation go in the system message.

Three levers: a specific role ("You are a ..."), clarity (format, length, audience, what to include and exclude, an example), and constraints (negative "Do NOT...", positive "Always...", conditional "If unsure, say so").

Output format is a contract once code reads the output. Name the keys and the types, and say "output only the JSON" so there's no preamble or code fences.

Temperature divides the logits before they become probabilities. Temperature 1 leaves the model's odds alone, below 1 sharpens toward the favorite token, and 0 always takes the top token. Top-p keeps the top tokens until their probabilities add up to p. Adjust one, not both. For tests: varied inputs, steady model.

Prompt patterns: persona, audience adaptation, template fill, few-shot, chain-of-thought, decomposition, critique, guardrail/boundary, meta-prompt. Anti-patterns: prompt injection, over-constraining, contradictory instructions, assuming one model's behavior works everywhere.

Lesson 01 build: phase11/01_prompt_harness.py. A call_claude() wrapper plus score_response() checking word limit, required keywords, and forbidden phrases. A vague vs engineered prompt experiment, 3 runs each, iterated until the engineered prompt passed 3/3 on every check.

Lesson 01 takeaways: you get only what you ask for. Numbers like "110 words" are targets, not limits, so ask for less than the real limit. The model cannot see your test criteria.

## Lesson 03: Structured Outputs

The reliability spectrum: prompt-based gives no guarantee. JSON mode guarantees valid syntax. Schema mode guarantees syntax, shape (keys), and types. Constrained decoding blocks invalid tokens while generating.

JSON Schema describes the shape of JSON: type, properties, required, enum, minimum and maximum, nested objects and arrays, $defs and $ref.

Pydantic turns a Python class into a schema with model_json_schema() and validates data with model_validate(). Literal[...] gives an enum. `str | None` with no default means required but may be null. Field(ge=, le=, max_length=, description=) adds limits.

Tool use as structured output: the tool's input_schema is your schema, tool_choice forces the call, and block.input is your data. Still validate afterward.

What schemas cannot catch: hallucinated values, missing items, dropped fields. Defenses: let null be a legal answer ("do not guess"), logic checks like weights summing to 100, and checking against the source.

Lesson 03 build: phase11/03_syllabus_extractor.py on the EECS 110 syllabus. Course has grade_components and deadlines as separate lists because weights belong to categories and dates belong to items. The grading table came out perfect, 8 components summing to 100%. A retry loop sends ValidationError text back as a tool_result with is_error true; 13 errors became 0 on the second attempt. It saves course.json.

Lesson 03 takeaways: quiz dates came out a week off, valid but wrong, and the date format drifted between runs. Fixes: a real date type, computing dates in code, and evals.

## Lesson 09: Function Calling & Tool Use

Core idea: Claude cannot do anything, it can only ask. When it needs a tool, its reply is a tool_use block requesting a function. Your code runs the real function and sends back a tool_result. Claude never executes anything.

stop_reason tells you which kind of reply you got. "tool_use" means run the requested tools, send the results, and call again. "end_turn" means Claude is done and the text is the answer.

Tool definitions have a name, a description, and an input_schema. The description is a prompt for when to use the tool: say what it returns and when it is useful. Vague descriptions cause wrong tool choices.

tool_choice: auto lets Claude decide, the default for chat. any means it must use some tool. {"type": "tool", "name": ...} forces that specific tool.

Parallel calls: one reply can contain several tool_use blocks. Run them all and send all results back in one message.

Errors and security: return errors as results so Claude can fix itself. Only expose the tools you need; the FUNCTIONS dict is the allowlist. Validate inputs, for example block `..` paths, which could expose ~/.bashrc and the API key. Never run model-written SQL or shell commands directly. Treat tool results as untrusted because they can carry prompt injection. Cap the loop with MAX_STEPS.

Lesson 09 build: phase11/09_course_assistant.py loads course.json and gives Claude get_today and get_deadlines. For "What's due in the next two weeks?" Claude called both tools in order, then answered.

Lesson 09 takeaways: the loop worked perfectly, but the answer inherited a wrong year from the extracted data and stretched "two weeks." Agents are only as good as their data.

The agent loop: call Claude with the conversation so far. If Claude gave a final answer, print it and stop. Otherwise run the tool it asked for, add the result to the conversation, and repeat.

## Lesson 05: Context Engineering

Core idea: everything sent to Claude (system prompt, tools, history, documents, the question) shares one limited context window. Context engineering decides what goes in, what stays out, and in what order.

The window is a budget. History grows every turn because every API call resends the whole conversation; Claude remembers nothing between calls. More is not better: a tight, relevant context beats a huge one full of junk.

Lost in the middle: models pay the most attention to the start and the end of the context. Put key rules first and the question plus best info last, with the least important material in the middle. Ranked documents 1 to 5 go in order 1, 3, 5, 4, 2.

Compression keeps the chat from getting expensive and slow: summarize old history and keep recent turns verbatim, use a sliding window that keeps only the last N turns (cheap but forgets older turns), filter out irrelevant documents, and prune tools to only the ones the question needs.

Memory types: short-term memory is the live conversation in the window. Long-term memory is saved facts per user, loaded into the system prompt each session, like CLAUDE.md. Episodic memory is past conversations, searched by similarity using embeddings.

Long-term memory vs system prompt: the system prompt is the fixed slot the developer writes for everyone. Long-term memory is content learned over time per user, saved in a file or database, and loaded into that slot each session.

Lesson 05 build: upgraded phase11/09_course_assistant.py into a multi-turn chat with a persistent history, printing response.usage.input_tokens each call. Added a get_grading tool so grade weights could reach the window. trim_history() keeps the last MAX_TURNS questions, cutting only at real user questions so tool_use and tool_result stay paired.

Lesson 05 takeaways: without trimming, tokens only climbed (790 to 2377). With trimming, turn 4 dropped from 2148 to 1144, but Claude had to call get_deadlines again because the old list was gone. Return everything when data is small; add filters when it is big. Date math belongs in code. Same question can give different answers, which is why evals exist.
