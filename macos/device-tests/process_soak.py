#!/usr/bin/env python3
import json,time
from module_support import ARTIFACT_DIR,assert_process,operation,positive_integer_environment,wait_for_process,write_json
duration=positive_integer_environment("OVERTE_DEVICE_IDLE_SECONDS",300,7200);interval=positive_integer_environment("OVERTE_DEVICE_SAMPLE_SECONDS",5,300)
operation("app.launch");identity=wait_for_process();started=time.monotonic();samples=[]
while int(time.monotonic()-started)<duration:
 elapsed=int(time.monotonic()-started);assert_process(identity,f"macOS soak after {elapsed}s");sample=operation("telemetry.snapshot");sample["elapsedSeconds"]=elapsed;samples.append(sample);time.sleep(interval)
assert_process(identity,"macOS soak completion")
with (ARTIFACT_DIR/"telemetry.jsonl").open("w",encoding="utf-8") as out:
 for sample in samples:out.write(json.dumps(sample,sort_keys=True)+"\n")
write_json("metrics.json",{"durationSeconds":duration,"processIdentity":identity,"samples":len(samples)});print(f"macOS process remained stable for {duration} seconds.")
