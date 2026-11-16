# v0.9 implementation verification

This directory preserves the first clean implementation-source CI receipts at
`6ae9e1bab3d38be99f36022c8627a67210cd17b4`. Both platform builds passed the
installed-wheel journey outside the checkout. Their uncompressed wheel files
are identical, although ZIP container hashes differ. The local targeted log
contains explicit integration skips; the separate CI jobs verify real services.

Documentation/evidence commits follow this source. The final GitHub Release
ships its own build receipts and SHA256SUMS for the exact downloadable assets.
These installation records do not establish a new performance or answer score.
See [the verification guide](../../../docs/verification-v0.9.0.md).
