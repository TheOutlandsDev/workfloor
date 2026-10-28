# v0.3 public source review

The target is the public TheOutlandsDev/workfloor repository, with a new v0.3.1
release. Changes are original recovery/ownership logic, its synthetic tests,
source packaging/CI and public documentation. The v1 database schema, import
rules, historical release tags, frozen v0.2 browser exports and media remain
separate. No employer system, source code, schema or record was consulted.

The packaging allowlist is a literal list in scripts/build_release.py. It includes
the original public application source and historical reviewed media, plus the
new reviewed source/docs/tests. The old root MANIFEST-SHA256.json and
RELEASE-CHECKSUMS.txt describe earlier publication and are excluded from this new
ZIP. Its generated SOURCE-MANIFEST.json and attached release receipt/checksums
describe the actual v0.3 package. Neither is a signature or proof of authorship.

Private/ignored database, lock, backup, browser installation and test-output
trees are never enumerated as release inputs. The original numeric recovery
receipt intentionally omits paths, timestamps, random IDs, secret tokens and
database bytes. Existing public screenshots/media are unchanged. Earlier public
release notes/validation are retained under explicit historical filenames.

Source checks include parsing, relative documentation links, the exact staged
inventory, a text privacy audit with any generic test/example findings dispositioned,
all functional tests and fresh package acceptance. Raw private logs and audit
reports stay outside GitHub. Final public ZIP bytes are compared with a local
build from the exact release source. Old releases are retained unchanged.
