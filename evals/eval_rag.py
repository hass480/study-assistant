from app import search
from app.assistant import MODEL, StudyAssistant, client

TEST_CASES = [
    {"q": "How do I stop the chat getting expensive?",
     "find": "compression",
     "expected": "Summarize old history, use a sliding window, filter irrelevant documents, prune tools."},
    {"q": "What's the difference between JSON mode and schema mode?",
     "find": "reliability spectrum",
     "expected": "JSON mode only guarantees valid JSON syntax; schema mode also guarantees the keys and types."},
    {"q": "What does temperature 0 do?",
     "find": "temperature divides",
     "expected": "The model always picks the top token, so output is as predictable as possible."},
    {"q": "Where should important information go in a long prompt?",
     "find": "lost in the middle",
     "expected": "At the start and end, because models pay less attention to the middle."},
    {"q": "What does it mean when stop_reason is tool_use?",
     "find": "stop_reason",
     "expected": "Claude wants a tool run; your code runs it, sends the result back, and calls again."},
    {"q": "Why does the conversation history keep growing?",
     "find": "window is a budget",
     "expected": "Every API call resends the whole conversation because Claude remembers nothing between calls."},
    {"q": "How do I install Python packages in my venv?",
     "find": "uv pip install",
     "expected": "Use uv pip install, because the venv was made with uv and has no pip."},
    {"q": "How is long-term memory different from the system prompt?",
     "find": "long-term memory vs system prompt",
     "expected": "The system prompt is fixed for everyone; long-term memory is learned per user and loaded into it."},
    {"q": "When is the EECS 110 final project due?", "answerable": False},
    {"q": "What's the best pizza place in Columbus?", "answerable": False},
]

GRADE_TOOL = {
    "name": "grade",
    "description": "Record a grade for the answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "reason": {"type": "string"},
        },
        "required": ["score", "reason"],
    },
}

RUBRIC = """Grade the ANSWER against the EXPECTED key points.
5: covers all key points correctly
4: correct, missing a minor detail
3: partly correct or missing a key point
2: mostly wrong or off-topic
1: wrong, or claims the info isn't available when it is"""


def judge(question, expected, answer):
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=RUBRIC,
        tools=[GRADE_TOOL],
        tool_choice={"type": "tool", "name": "grade"},
        messages=[{"role": "user", "content":
                   f"QUESTION: {question}\n\nEXPECTED: {expected}\n\nANSWER: {answer}"}],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    return block.input["score"], block.input["reason"]


def run_eval():
    assistant = StudyAssistant(use_cache=False)
    retrieval_hits = answer_passes = answerable = refusals_ok = unanswerable = 0

    for case in TEST_CASES:
        reply = assistant.ask(case["q"])["answer"]

        if case.get("answerable", True):
            answerable += 1
            chunks = [chunk.lower() for score, chunk in search.search(case["q"], 3)]
            hit = any(case["find"] in c for c in chunks)
            score, reason = judge(case["q"], case["expected"], reply)
            retrieval_hits += hit
            answer_passes += score >= 4
            print(f"{'HIT ' if hit else 'MISS'}  score {score}  {case['q']}")
            if score < 4:
                print(f"      judge: {reason}")
        else:
            unanswerable += 1
            refused = "not in my notes" in reply.lower()
            refusals_ok += refused
            print(f"{'REFUSED' if refused else 'ANSWERED!'}  {case['q']}")

    print(f"\nRetrieval:  {retrieval_hits}/{answerable} found the right note")
    print(f"Answers:    {answer_passes}/{answerable} scored 4+")
    print(f"Refusals:   {refusals_ok}/{unanswerable} correctly said 'not in my notes'")


if __name__ == "__main__":
    run_eval()
