import groovy.json.JsonSlurper
import java.util.concurrent.TimeUnit

// Used directly by Gradle and the host consumer tests. No Gradle/build process
// is needed to resolve inputs; stderr must not disclose external graph paths.
return { File picoRoot ->
    def process = new ProcessBuilder('python3',
        new File(picoRoot, 'release/pico-source-inputs.py').absolutePath,
        '--pico-root', picoRoot.canonicalPath).start()
    def output = new StringBuffer()
    def errors = new StringBuffer()
    def stdoutReader = process.consumeProcessOutputStream(output)
    def stderrReader = process.consumeProcessErrorStream(errors)
    if (!process.waitFor(120, TimeUnit.SECONDS)) {
        process.destroyForcibly()
        throw new IllegalStateException('PICO_SOURCE_INPUTS_TIMEOUT')
    }
    stdoutReader.join()
    stderrReader.join()
    if (process.exitValue() != 0) {
        throw new IllegalStateException('PICO_SOURCE_INPUTS_REJECTED')
    }
    def inputs = new JsonSlurper().parseText(output.toString())
    if (inputs.status != 'PICO_INPUT_BYTES_BOUND_NATIVE_VERIFICATION_PENDING') {
        throw new IllegalStateException('PICO_SOURCE_INPUTS_STATUS')
    }
    inputs
}
