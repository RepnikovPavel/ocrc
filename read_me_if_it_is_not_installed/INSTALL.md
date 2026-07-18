# Installing ocrc without the one-liner

ocrc is a single Python file with no dependencies, so "installing" means putting
it somewhere on your PATH.

## From a clone

```sh
git clone https://github.com/RepnikovPavel/ocrc.git
cd ocrc
sh install.sh                      # honours OCRC_BIN_DIR
```

## By hand

```sh
curl -fsSL https://raw.githubusercontent.com/RepnikovPavel/ocrc/main/dont_read_me_src/ocrc.py \
  -o ~/.local/bin/ocrc
chmod +x ~/.local/bin/ocrc
```

## Without installing at all

```sh
python3 dont_read_me_src/ocrc.py parse paper.pdf
```

## Choosing where it lands

`install.sh` writes to `/usr/local/bin` when that is writable, otherwise to
`~/.local/bin`. Override with `OCRC_BIN_DIR=/somewhere sh install.sh`. If the
directory is not on your PATH the installer says so instead of leaving you with
a command that appears to be missing.

## Requirements

- `python3 >= 3.8` — checked by the installer
- a reachable dots.mocr service; set `OCRC_SERVER`

Nothing else. If a step suggests `pip install`, something has gone wrong: ocrc
imports only the standard library, and that is deliberate — it is what lets an
agent drop the file on an arbitrary machine and call it.
