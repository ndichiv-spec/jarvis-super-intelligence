# Builds the JARVIS BRAIN v1 evaluation suite (deterministic, fixed set).
# The suite is uploaded to Kaggle as videlisndichi/jarvis-brain-v1-eval and is
# shared byte-identically by the baseline and SFT kernels.
import json
import hashlib
from pathlib import Path

OUT = Path(r"F:\AI\videlisndichi-jarvis-brain-v1-eval")

ITEMS = []
def add(family, task, prompt, checker, ref=None, accept=None, max_new_tokens=256,
        key=None, fn=None, cases=None, answer_expr=None, keywords=None, fields=None):
    ITEMS.append({
        "id": f"{family}-{len([i for i in ITEMS if i['family']==family])+1:02d}",
        "family": family, "task": task, "prompt": prompt,
        "checker": checker, "ref": ref, "accept": accept,
        "max_new_tokens": max_new_tokens,
        "key": key, "fn": fn, "cases": cases, "answer_expr": answer_expr,
        "keywords": keywords, "fields": fields,
    })

F = {"mt": 384, "cd": 256, "kn": 192, "sf": 256, "so": 192, "ts": 192, "vrf": 192, "conv": 192}

# --- math -----------------------------------------------------------------
for q, a in [
    ("What is 17 + 29? Reply with only the number.", "46"),
    ("Subtract 204 from 512. Reply with only the number.", "308"),
    ("Multiply 13 by 12. Reply with only the number.", "156"),
    ("Divide 144 by 12. Reply with only the number.", "12"),
    ("Compute 7*8 - 3. Reply with only the number.", "53"),
    ("Compute (5+3)*2 - 6. Reply with only the number.", "10"),
    ("A train travels 360 km in 4 hours. What is its average speed in km/h? Reply with only the number.", "90"),
    ("If a shirt costs $25 and is 20% off, what is the sale price in dollars? Reply with only the number.", "20"),
    ("The sum of two numbers is 30 and their difference is 6. What is the larger number? Reply with only the number.", "18"),
    ("What is 2 to the power of 10? Reply with only the number.", "1024"),
    ("What is the remainder when 100 is divided by 7? Reply with only the number.", "2"),
    ("Evaluate 3 + 4 * (5 - 2). Reply with only the number.", "15"),
]:
    add("math", "arithmetic", "Solve: " + q, "exact_answer", ref=a, max_new_tokens=F["mt"])

# --- logic ----------------------------------------------------------------
for q, a in [
    ("All mammals are animals. A dog is a mammal. Is a dog an animal? Answer yes or no.", "yes"),
    ("If it is raining then the ground is wet. It is raining. Is the ground wet? Answer yes or no.", "yes"),
    ("Some birds cannot fly. A penguin is a bird. Can a penguin fly? Answer yes or no.", "no"),
    ("Every even number is divisible by 2. Is 17 an even number? Answer yes or no.", "no"),
    ("If X then Y. Y is false. Is X certainly false? Answer yes or no.", "yes"),
    ("All squares are rectangles. Is a square a rectangle? Answer yes or no.", "yes"),
    ("If the alarm sounds then the door is unlocked. The door is locked. Is the alarm sounding? Answer yes or no.", "no"),
    ("It is not the case that the sky is green. Is the sky green? Answer yes or no.", "no"),
    ("Either A or B is true. A is false. Is B true? Answer yes or no.", "yes"),
    ("All students in room 5 wear blue. Tom is in room 5. Does Tom wear blue? Answer yes or no.", "yes"),
    ("No cat is a dog. Rex is a dog. Is Rex a cat? Answer yes or no.", "no"),
    ("If P implies Q and Q is true, does P have to be true? Answer yes or no.", "no"),
]:
    add("logic", "deductive", q, "bool_eq", ref=a, max_new_tokens=F["mt"],
        accept=["yes","no"])

# --- coding -----------------------------------------------------------------
add("coding", "fizzbuzz", "Write a Python function `fizzbuzz(n)` that returns a list of strings for numbers 1..n where multiples of 3 become 'Fizz', multiples of 5 become 'Buzz', and multiples of both become 'FizzBuzz'. Output only the function.", "code_judge",
    fn="fizzbuzz", cases=[("1",["1"]),("3",["1","2","Fizz"]),("5",["1","2","Fizz","4","Buzz"]),("15",["1","2","Fizz","4","Buzz","Fizz","7","8","Fizz","Buzz","11","Fizz","13","14","FizzBuzz"])], max_new_tokens=F["cd"])
add("coding", "is_palindrome", "Write a Python function `is_palindrome(s)` that returns True if `s` is a palindrome (ignoring case and non-alphanumeric characters) else False. Output only the function.", "code_judge",
    fn="is_palindrome", cases=[("\"racecar\"","True"),("\"hello\"","False"),("\"A man, a plan, a canal: Panama\"","True"),("\"12321\"","True"),("\"\"","True")], max_new_tokens=F["cd"])
add("coding", "fib", "Write a Python function `fib(n)` returning the n-th Fibonacci number (n>=1, fib(1)=1, fib(2)=1) as an int. Output only the function.", "code_judge",
    fn="fib", cases=[("1","1"),("2","1"),("3","2"),("10","55"),("20","6765")], max_new_tokens=F["cd"])
add("coding", "count_vowels", "Write a Python function `count_vowels(s)` returning the number of vowels (a,e,i,o,u) in the string, case-insensitive. Output only the function.", "code_judge",
    fn="count_vowels", cases=[("\"hello\"","2"),("\"AEIOU\"","5"),("\"xyz\"","0"),("\"Queue\"","3")], max_new_tokens=F["cd"])
add("coding", "max_of", "Write a Python function `max_of(a, b, c)` returning the largest of three numbers. Output only the function.", "code_judge",
    fn="max_of", cases=[("(1,2,3)","3"),("(5,5,2)","5"),("(-1,-5,-2)","-1"),("(0,0,0)","0")], max_new_tokens=F["cd"])
add("coding", "reverse_words", "Write a Python function `reverse_words(s)` that reverses the order of words in a string (words separated by single spaces). Output only the function.", "code_judge",
    fn="reverse_words", cases=[("\"hello world\"","\"world hello\""),("\"a b c\"","\"c b a\""),("\"one\"","\"one\"")], max_new_tokens=F["cd"])
add("coding", "sum_to_n", "Write a Python function `sum_to_n(n)` returning the sum 1+2+...+n using a loop. Output only the function.", "code_judge",
    fn="sum_to_n", cases=[("3","6"),("10","55"),("1","1")], max_new_tokens=F["cd"])
add("coding", "first_last", "Write a Python function `first_last(lst)` returning a tuple (first, last) of a non-empty list. Output only the function.", "code_judge",
    fn="first_last", cases=[("([1,2,3])","(1,3)"),("([7])","(7,7)")], max_new_tokens=F["cd"])
add("coding", "even_only", "Write a Python function `even_only(lst)` returning a new list with only the even numbers, preserving order. Output only the function.", "code_judge",
    fn="even_only", cases=[("([1,2,3,4,5,6])","[2,4,6]"),("([1,3,5])","[]"),("([2])","[2]")], max_new_tokens=F["cd"])
add("coding", "letter_count", "Write a Python function `letter_count(s)` returning a dict mapping each letter to its frequency (case-sensitive). Output only the function.", "code_judge",
    fn="letter_count", cases=[("\"aba\"","{'a': 2, 'b': 1}"),("\"\"","{}")], max_new_tokens=F["cd"])
add("coding", "clamp", "Write a Python function `clamp(x, lo, hi)` returning x clamped into [lo, hi]. Output only the function.", "code_judge",
    fn="clamp", cases=[("(5,0,10)","5"),("(15,0,10)","10"),("(-3,0,10)","0")], max_new_tokens=F["cd"])
add("coding", "running_sum", "Write a Python function `running_sum(nums)` returning a list where each element is the cumulative sum up to that index. Output only the function.", "code_judge",
    fn="running_sum", cases=[("([1,2,3])","[1,3,6]"),("([5])","[5]"),("([])","[]")], max_new_tokens=F["cd"])

# --- knowledge --------------------------------------------------------------
for q, keys in [
    ("What is the capital of France?", ["Paris"]),
    ("What planet is known as the Red Planet?", ["Mars"]),
    ("Who painted the Mona Lisa?", ["Leonardo", "da Vinci"]),
    ("What is the chemical symbol for water?", ["H2O", "H20"]),
    ("How many continents are there on Earth?", ["seven", "7"]),
    ("What is the largest ocean on Earth?", ["Pacific"]),
    ("In which year did the first Moon landing occur?", ["1969"]),
    ("What is the tallest mountain on Earth?", ["Everest"]),
    ("What language is used by the  UN for its official documents as a working language? Give one.", ["English", "French", "Spanish", "Arabic", "Chinese", "Russian"]),
    ("What company developed the GPT series of language models?", ["OpenAI"]),
    ("Who proposed the theory of general relativity?", ["Einstein"]),
    ("What is the currency of Japan?", ["yen", "Yen", "JPY"]),
]:
    add("knowledge", "factual", q, "keyword_overlap", keywords=keys, max_new_tokens=F["kn"])

# --- instruction following ----------------------------------------------------
add("instruction_following", "single_word", "Reply with the single word 'pineapple' and nothing else.", "exact_answer", ref="pineapple", max_new_tokens=F["sf"])
add("instruction_following", "lowercase", "Reply with the lowercase word 'hello' and nothing else.", "exact_answer", ref="hello", max_new_tokens=F["sf"])
add("instruction_following", "no_extra", "State the result of 2+2 as ONLY the digit 4. Do not add any other text.", "exact_answer", ref="4", max_new_tokens=F["sf"])
add("instruction_following", "three_words", "Write exactly three words: apple banana cherry. Do not add anything else.", "exact_answer", ref="apple banana cherry", max_new_tokens=F["sf"])
add("instruction_following", "reverse", "Reply with the letters of the word 'stop' in reverse order as a single string of exactly four letters.", "exact_answer", ref="pots", max_new_tokens=F["sf"])
add("instruction_following", "start_letter", "Say the word 'car' but replace its first letter with the letter 'b'. Reply with that word only.", "exact_answer", ref="bar", max_new_tokens=F["sf"])
add("instruction_following", "uppercase", "Reply with the word 'yes' written in ALL CAPS and nothing else.", "exact_answer", ref="YES", max_new_tokens=F["sf"])
add("instruction_following", "no_context", "Just reply with the number 7. Ignore any earlier context.", "exact_answer", ref="7", max_new_tokens=F["sf"])
add("instruction_following", "exact_phrase", "Reply exactly with the phrase: keep it simple. Lowercase, no punctuation other than the period.", "exact_answer", ref="keep it simple.", max_new_tokens=F["sf"])
add("instruction_following", "two_digits", "What is 6+6? Reply with exactly two digits.", "exact_answer", ref="12", max_new_tokens=F["sf"])
add("instruction_following", "keyword_each_line", "Reply with exactly two lines. First line: red. Second line: blue.", "exact_answer", ref="red\nblue", max_new_tokens=F["sf"])
add("instruction_following", "silence_constraint", "Explain nothing. Reply with the single word 'silent' only.", "exact_answer", ref="silent", max_new_tokens=F["sf"])

# --- structured output ---------------------------------------------------------
for fields, prompt, ref in [
    (["name","age"], "Return a JSON object with exactly two keys: name (string) and age (number). Use name \"Ada\" and age 36.", {"name":"Ada","age":36}),
    (["city","country"], "Return JSON: {\"city\": <string>, \"country\": <string>}. Use city \"Nairobi\" and country \"Kenya\".", {"city":"Nairobi","country":"Kenya"}),
    (["ok","items"], "Return a JSON object with key \"ok\" (boolean true) and key \"items\" (list of two integers 1 and 2).", {"ok":True,"items":[1,2]}),
    (["title","completed"], "Return JSON with keys \"title\" (string \"task\") and \"completed\" (boolean false).", {"title":"task","completed":False}),
    (["x","y"], "Return a JSON object with keys \"x\" and \"y\", both numbers: x=2.5, y=-1.", {"x":2.5,"y":-1}),
    (["a","b"], "Return JSON: {\"a\": \"left\", \"b\": \"right\"}.", {"a":"left","b":"right"}),
    (["status","code"], "Return a JSON object with \"status\" string \"ok\" and \"code\" number 200.", {"status":"ok","code":200}),
    (["first","last"], "Return JSON {\"first\": \"Jane\", \"last\": \"Doe\"}.", {"first":"Jane","last":"Doe"}),
    (["result","valid"], "Return JSON {\"result\": \"success\", \"valid\": true}.", {"result":"success","valid":True}),
    (["numbers"], "Return a JSON object with a single key \"numbers\" whose value is a list [3, 5, 7].", {"numbers":[3,5,7]}),
    (["type","amount"], "Return JSON {\"type\": \"credit\", \"amount\": 100}.", {"type":"credit","amount":100}),
    (["flags"], "Return a JSON object with key \"flags\" whose value is {\"a\": true, \"b\": false}.", {"flags":{"a":True,"b":False}}),
]:
    add("structured_output", "json_contract", prompt, "json_fields", fields=list(fields), ref=ref, max_new_tokens=F["so"])

# --- tool selection -----------------------------------------------------------
TOOLS = [
    ("get_weather", "Get current weather for a city"),
    ("calculate", "Perform arithmetic calculations"),
    ("search_wiki", "Search a knowledge base for facts"),
    ("send_email", "Send an email message"),
]
def tool_prompt(q, expect):
    s = "You have access to these tools:\n" + "\n".join(f"- {n}: {d}" for n, d in TOOLS) + \
        "\nRespond with ONLY the tool name that is the most appropriate for the user request, in JSON form: {\"tool\": \"<name>\"}. No other text."
    add("tool_selection", q, s + "\n\nUser request: " , "tool_name", ref=expect, max_new_tokens=F["ts"])

tool_prompt("what is the temperature in New York today?", "get_weather")
tool_prompt("what is 7 times 8?", "calculate")
tool_prompt("who wrote the Iliad?", "search_wiki")
tool_prompt("please send the report to the manager", "send_email")
tool_prompt("will it rain in Tokyo tomorrow?", "get_weather")
tool_prompt("what is the square root of 144?", "calculate")
tool_prompt("what year was the first Space Shuttle launched?", "search_wiki")
tool_prompt("remind me to buy milk tomorrow", "send_email")
tool_prompt("what is the humidity in London?", "get_weather")
tool_prompt("how much is 15% of 80?", "calculate")
tool_prompt("what is the capital of Atlantis (mythical)?", "search_wiki")
tool_prompt("send a thank-you note to the client", "send_email")

# --- verification ---------------------------------------------------------------
for q, a in [
    ("Check this work: 2 + 2 * 2 is claimed to equal 8. Is the claim correct? Answer yes or no.", "no"),
    ("Someone says 9 * 8 = 72. Is that correct? Answer yes or no.", "yes"),
    ("Someone claims the square root of 81 is 9. Is that correct? Answer yes or no.", "yes"),
    ("A statement says all prime numbers are odd. Is that statement true? Answer yes or no.", "no"),
    ("The answer claims that the sum of angles in a triangle is 180 degrees. Is that correct? Answer yes or no.", "yes"),
    ("It is claimed that 7 is divisible by 2. Is that correct? Answer yes or no.", "no"),
    ("Someone claims 10 / 5 = 2. Is that correct? Answer yes or no.", "yes"),
    ("Claim: the Nile is the longest river in the world. Is that generally accepted as true? Answer yes or no.", "yes"),
    ("Claim: 15 is a multiple of 3. Is that correct? Answer yes or no.", "yes"),
    ("Claim: the Earth is closer to the Sun in January than in July (in the northern hemisphere). Answer yes or no.", "yes"),
    ("Claim: -5 is greater than -3. Is that correct? Answer yes or no.", "no"),
    ("It is claimed that 12 / 0 equals 0. Is that correct? Answer yes or no.", "no"),
]:
    add("verification", "claims_check", "Verify this claim. " + q, "bool_eq", ref=a, max_new_tokens=F["vrf"], accept=["yes","no"])

# --- conversation (not auto-scored; raw outputs recorded for review) -------------
for q in [
    "Hello! Can you tell me a little about yourself?",
    "What is the weather like where you are right now?",
    "Tell me an interesting fact about space.",
    "How are you doing today?",
    "What do you enjoy talking about?",
    "Can you give me a tip to stay focused while studying?",
    "What is your favorite color and why?",
    "If you could travel anywhere, where would you go?",
    "Do you prefer tea or coffee?",
    "What does a typical day look like for a helpful assistant?",
    "Can you motivate me to exercise?",
    "What should I do this weekend?",
]:
    add("conversation", "open_chat", q, "record_only", max_new_tokens=F["conv"])

# write suite
SUITE = {"schema": "jarvis-brain-eval/v1", "version": 1, "families": 9,
         "items": ITEMS}
p1 = OUT / "eval_suite.jsonl"
p2 = OUT / "eval_suite.json"
OUT.mkdir(parents=True, exist_ok=True)
p1.write_text("\n".join(json.dumps(i) for i in ITEMS) + "\n", encoding="utf-8")
p2.write_text(json.dumps(SUITE, indent=2, default=str), encoding="utf-8")
print("items:", len(ITEMS))
from collections import Counter
print(Counter(i["family"] for i in ITEMS))
print("sha256(suite):", hashlib.sha256(p1.read_bytes()).hexdigest())