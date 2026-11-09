# bracket-mass: the change record

## Revision 1, e6011872895f, 2026-11-02T12:31:40.437764Z

- created from bracket-ge@062d2957e32a
- product name: 'The engine bracket' -> 'The engine bracket with a mass demand'
- product purpose: 'A bracket that carries a hanging load from a pin to a flat mounting face bolted to a frame: the GE aircraft engine bracket challenge scaled to a polymer part' -> 'The engine bracket on a frame that moves, where every gram counts: as printed it weighs at most the mass demand, every other requirement as first given'
- design: bracket-ge@v4 -> bracket-mass@v1
- brief may_change: ["lug_thickness", "fillet_radius", "underside_angle"] -> ["lug_thickness", "fillet_radius", "underside_angle", "shape"]
- brief text: "A bracket that carries a hanging load from a pin to a flat mounting face bolted to a frame. It is loaded in four ways during handling, each for a short time. It is printed in PLA on the lab's Prusa CORE One+ in a small series. The mounting face must sit flat against the frame and the bolt holes must meet the frame's pattern. Low mass is wanted but strength comes first." -> "A bracket that carries a hanging load from a pin to a flat mounting face bolted to a frame. It is loaded in four ways during handling, each for a short time. It is printed in PLA in a small series on the printers available. The mounting face must sit flat against the frame and the bolt holes must meet the frame's pattern. The bracket goes on a frame that moves, where every gram counts: as printed it may weigh no more than the mass requirement of the design says, with every other requirement as first given. Its shape is free within the envelope, the interfaces kept; print time is the objective once the requirements are met."
- mandate M6: held -> interval to 0.85
- mandate M7: held -> interval to 0.85
- mandate M8: held -> interval to 0.85
- mandate M9: held -> interval to 0.85
- value M13: at most 40 g -> at most 16 g
- mandate M13: release -> interval, as needed
- metric M13 changed: class, text, source
- value M14: at most 4380 s -> at most 4560 s
- value M15: at most 23 g -> at most 25 g
- binding O2 in bracket-mass@v1: +mount-face (declared, confirmed)
- binding O3 in bracket-mass@v1: +mount-edge (declared, confirmed)
- binding O4 in bracket-mass@v1: +bolt-hole-1 (declared, confirmed), +bolt-hole-2 (declared, confirmed), +bolt-hole-3 (declared, confirmed), +bolt-hole-4 (declared, confirmed)
- binding O5 in bracket-mass@v1: +pin-hole (declared, confirmed)
- binding O6 in bracket-mass@v1: +lug (declared, confirmed)
- binding O7 in bracket-mass@v1: +lug-underside (declared, confirmed)
- binding O8 in bracket-mass@v1: +web (declared, confirmed)
- binding O9 in bracket-mass@v1: +fillet-lug-mount (declared, confirmed)

## Revision 2, ae032df9d90f, 2026-11-02T12:31:40.458736Z

the held case: the mass demand held (experiments/h1-bracket-mass-held.json)

- mandate M13: interval, as needed -> held

## Revision 3, 37180c0d1180, 2026-11-09T19:09:04.258053Z

the mass case (experiments/h1-bracket-mass.json)

- form: order 1 -> order 2: the mandates moved from the metrics to the order's section, the brief's text, objective and quantity to the order's brief
- object O6 (lug): fixed -> free
- object O7 (lug underside): fixed -> free
- object O9 (fillet lug mount): fixed -> free
- mandate M13: held -> interval, as needed

## Revision 4, 51293041b166, 2026-11-09T19:09:04.270394Z

the held case: the mass demand held, the order declined on the evidence (experiments/h1-bracket-mass-held.json)

- answering: park -> decline
- mandate M13: interval, as needed -> held
