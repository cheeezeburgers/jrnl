# clack-bash selector for jrnl

Source: https://github.com/ibrahimhajjaj/clack-bash
Pinned commit: `afe36b88ab574b14a7bbc05ed1707fb4d9849ee5`.
Upstream's version function reports 1.2.0 (its header says 1.1.0).
Upstream identifies the code as MIT in both clack.sh and README.md.
Attribution and the MIT terms are preserved here and embedded in select.sh,
so the installed copy carries them without a separate license dependency.

This is a minimal adaptation of upstream `clack_select`, its key reader,
cursor helpers, symbols and colors. It retains the selector rendering,
wraparound, Enter, CSI/SS3 arrow sequences, and lower/uppercase j/k.
Other keys decoded by upstream's reader are still ignored by this selector;
Tab completion belongs to jrnl's Readline prompts.

Changes:
- Accept an explicit zero-based initial index after the message.
- Keep plain enabled choices only; omit unused widgets and rich-option parsing.
- Read stdin (terminal or pipe), return failure on EOF, and isolate signal/EXIT
  traps in the selector's subshell so jrnl's lock cleanup is untouched.
- Avoid cursor escape codes on redirected/dumb output and honor NO_COLOR.
- Use literal printf output rather than interpreting backslashes in labels.

The selected code uses indexed arrays and integer read timeouts supported by
macOS Bash 3.2. Upstream's blanket Bash 4 recommendation is omitted: this subset
does not need newer Bash. No namerefs, associative arrays, external UI commands,
or global initialization/cleanup traps are loaded.
