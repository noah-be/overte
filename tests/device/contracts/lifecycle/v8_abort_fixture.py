"""Export the real engine abort state/method into explicit host ownership seams."""
def write_abort_fixture(root, scratch):
    header = (root / 'libraries/script-engine/src/v8/ScriptEngineV8.h').read_text()
    state = next(line for line in header.splitlines() if 'std::atomic<bool> _abortRequested' in line)
    state += '\n' + next(line for line in header.splitlines() if 'bool isEvaluationAborted() const' in line)
    source = (root / 'libraries/script-engine/src/v8/ScriptEngineV8.cpp').read_text()
    method = 'void ScriptEngineV8::abortEvaluation(' + source.split(
        'void ScriptEngineV8::abortEvaluation(', 1)[1].split('\n}', 1)[0] + '\n}\n'
    (scratch / 'abort-state.inc').write_text(state)
    (scratch / 'abort-method.inc').write_text(method)
