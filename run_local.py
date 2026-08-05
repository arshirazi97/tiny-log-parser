"""Generate predictions from ./merged with plain transformers. No vLLM."""
import json, time, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from train2 import build_messages

tok = AutoTokenizer.from_pretrained("./merged")
model = AutoModelForCausalLM.from_pretrained(
    "./merged", torch_dtype=torch.bfloat16, device_map="cuda")
model.eval()

rows = [json.loads(l) for l in open("test.jsonl")][:200]
out = []
t0 = time.time()
for i, r in enumerate(rows):
    text = tok.apply_chat_template(
        build_messages(r["input"]), tokenize=False,
        add_generation_prompt=True, enable_thinking=False)
    ids = tok(text, return_tensors="pt").to("cuda")
    with torch.no_grad():
        gen = model.generate(**ids, max_new_tokens=300, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    out.append(tok.decode(gen[0][ids.input_ids.shape[1]:], skip_special_tokens=True))
    if i % 25 == 0:
        print(f"  {i}/{len(rows)}")

json.dump({"outputs": out, "elapsed": time.time() - t0}, open("local_raw.json", "w"))
print(f"done in {time.time()-t0:.0f}s  ({(time.time()-t0)/len(rows)*1000:.0f} ms/item)")
