The unchanged public-domain GifCreator 2016.11 header is stored without byte
changes inside `GifCreator.zip` and copied from
https://build-deps.overte.org/dependencies/GifCreator.zip, the production URL in
`nix/gif_creator.nix`. The header SHA256 is
`275e4fd71a1d3bdc80279aee59d6abf530d628ea77aec01a2cd155220be2c8be`.
The copyright and public-domain declaration remain in the header.

This fixture executes the actual production encoder without downloading code
during a mandatory host test. It does not replace the native render boundary.
