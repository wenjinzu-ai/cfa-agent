import pathlib
p = pathlib.Path(r"D:\code\cfa-agent\src\core\agent.py")
c = p.read_text(encoding="utf-8")
idx_start = c.find("async def _synthesize_result")
idx_end = c.find(chr(10) + "    async def _write_audit", idx_start)
old = c[idx_start:idx_end]
new = old.replace(
    "completed_results = [\n",
    "completed_steps = [s for s in plan.steps if s.status == StepStatus.DONE and s.result]\n            if len(completed_steps) == 1:\n                return str(completed_steps[0].result)\n            completed_results = [\n"
).replace(
    "for s in plan.steps\n",
    "for s in completed_steps\n"
)
c = c[:idx_start] + new + c[idx_end:]
p.write_text(c, encoding="utf-8")
print("OK")