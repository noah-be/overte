# QEMU low-power diagnostic profile

This profile provides a quick, non-production rendering check for macOS guests
without accelerated graphics. It wraps an existing `Overte.app`; it does not
replace or rebuild the executable.

The launcher selects forward rendering, a 0.25 viewport scale, one sample,
low-detail LOD and the eco refresh-rate profile. Shadows, haze, bloom, ambient
occlusion, local lighting and procedural materials are disabled. Startup,
networking, entity loading and scripting still use the production executable.

This profile must never be used as visual release evidence. The normal macOS
smokes intentionally retain their production scene, camera, renderer and image
validation criteria.

To assemble a package, place the unchanged existing `Overte.app`,
`qemu-low-power.js`, and an executable copy of `Overte-qemu-launcher.sh` in one
directory. Keeping the launcher outside the bundle preserves the application's
original code signature. The launcher can be named `Start Overte QEMU.command`
to make it directly launchable from Finder.

`Collect-Overte-Diagnostics.command` gathers the guest graphics description,
process state, unified Overte log, and recent application-log paths into one
text file beside the collector. It permits diagnosis without SSH or manually
typing Terminal commands in the guest.
