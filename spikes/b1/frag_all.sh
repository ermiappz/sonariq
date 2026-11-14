#!/bin/sh
# Spike B1: convert every deck IFC to .frag, one process each, capped at 3.6 GB so the VM's other services survive.
# Output: data/rcrv/spike_b1/frag/deck_<n>.frag and frag_convert.jsonl (one JSON line per deck).
cd "$(dirname "$0")"
D=../../data/rcrv/spike_b1
mkdir -p $D/frag
: > $D/frag_convert.jsonl
for n in 7 5 6 4 2 3 1; do
  systemd-run --user --scope -q -p MemoryMax=3600M -p MemorySwapMax=0 \
    node --max-old-space-size=3000 frag_convert.mjs $D/ifc/rcrv_deck_${n}_full.ifc $D/frag/deck_$n.frag >> $D/frag_convert.jsonl 2>$D/frag_convert_$n.err \
    || echo "{\"src\":\"rcrv_deck_${n}_full.ifc\",\"failed\":true,\"exit\":$?}" >> $D/frag_convert.jsonl
done
