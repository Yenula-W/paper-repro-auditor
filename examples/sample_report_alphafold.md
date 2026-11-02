# Reproducibility audit: Highly accurate protein structure prediction with AlphaFold

- **Identifier:** 10.1038/s41586-021-03819-2
- **Venue / date:** Nature / 2021-07-15
- **Full text:** europepmc:PMC8371605
- **Score:** 86/100 (9 pass, 1 warn, 1 fail)

## Checklist

| | Check | Status | Detail |
|---|---|---|---|
| ✅ | Full text retrieved | PASS | europepmc:PMC8371605 |
| ✅ | Data availability statement | PASS | All input data are freely available from public sources. Structures from the PDB were used for training and as templates (https://www.wwpdb.org/ftp/pdb-ftp-sites; for the associated sequence data and  |
| ✅ | Code availability statement | PASS | Source code for the AlphaFold model, trained weights and inference script are available under an open-source license at https://github.com/deepmind/alphafold. Neural networks were developed with Tenso |
| ✅ | No 'available on request' | PASS |  |
| ✅ | Code link present | PASS | https://github.com/deepmind/alphafold |
| ❌ | All links resolve | FAIL | dead: https://cdn.rcsb.org/resources/sequence/clusters/bc-40.out (404), https://ftp.wwpdb.org/pub/pdb/derived_data/ (0) |
| ⚠️ | Code archived with DOI | WARN | only bare git-host links (no Zenodo/SWH snapshot) |
| ✅ | Code has a license | PASS | Apache-2.0 |
| ✅ | Version/tag matching paper | PASS | https://github.com/deepmind/alphafold: v2.0.0 |
| ✅ | Repo light checks | PASS | deps, README run steps, entry point, license |
| ✅ | Data deposited | PASS | https://cdn.rcsb.org/resources/sequence/clusters/bc-40.out, https://ftp.ebi.ac.uk/pub/databases/uniprot/previous_releases/release-2020_01/uniref/, https://ftp.ebi.ac.uk/pub/databases/metagenomics/peptide_database/2018_12/ |

## Availability statements

**Code availability** (code)

> Source code for the AlphaFold model, trained weights and inference script are available under an open-source license at https://github.com/deepmind/alphafold. Neural networks were developed with TensorFlow v.1 (https://github.com/tensorflow/tensorflow), Sonnet v.1 (https://github.com/deepmind/sonnet), JAX v.0.1.69 (https://github.com/google/jax/) and Haiku v.0.0.4 (https://github.com/deepmind/dm-haiku). The XLA compiler is bundled with JAX and does not have a separate version number. For MSA search on BFD+Uniclust30, and for template search against PDB70, we used HHBlits and HHSearch from hh-suite v.3.0-beta.3 release 14/07/2017 (https://github.com/soedinglab/hh-suite). For MSA search on UniRef90 and clustered MGnify, we used jackhmmer from HMMER v.3.3 (http://eddylab.org/software/hmmer/). For constrained relaxation of structures, we used OpenMM v.7.3.1 (https://github.com/openmm/openmm) with the Amber99sb force field. Construction of BFD used MMseqs2 v.925AF (https://github.com/soedinglab/MMseqs2) and FAMSA v.1.2.5 (https://github.com/refresh-bio/FAMSA). Data analysis used Python v.3.6 (https://www.python.org/), NumPy v.1.16.4 (https://github.com/numpy/numpy), SciPy v.1.2.1 (https

**Data availability** (data)

> All input data are freely available from public sources. Structures from the PDB were used for training and as templates (https://www.wwpdb.org/ftp/pdb-ftp-sites; for the associated sequence data and 40% sequence clustering see also https://ftp.wwpdb.org/pub/pdb/derived_data/ and https://cdn.rcsb.org/resources/sequence/clusters/bc-40.out). Training used a version of the PDB downloaded 28 August 2019, while the CASP14 template search used a version downloaded 14 May 2020. The template search also used the PDB70 database, downloaded 13 May 2020 (https://wwwuser.gwdg.de/~compbiol/data/hhsuite/databases/hhsuite_dbs/). We show experimental structures from the PDB with accession numbers 6Y4F <http://doi.org/10.2210/pdb6Y4F/pdb>77, 6YJ1 <http://doi.org/10.2210/pdb6YJ1/pdb>78, 6VR4 <http://doi.org/10.2210/pdb6VR4/pdb>79, 6SK0 <http://doi.org/10.2210/pdb6SK0/pdb>80, 6FES <http://doi.org/10.2210/pdb6FES/pdb>81, 6W6W <http://doi.org/10.2210/pdb6W6W/pdb>82, 6T1Z <http://doi.org/10.2210/pdb6T1Z/pdb>83 and 7JTL <http://doi.org/10.2210/pdb7JTL/pdb>84. For MSA lookup at both the training and prediction time, we used UniRef90 v.2020_01 (https://ftp.ebi.ac.uk/pub/databases/uniprot/previous_releases/


## Links

| URL | Type | Alive | Archived DOI | License | Version | Notes |
|---|---|---|---|---|---|---|
| https://github.com/deepmind/alphafold | github/code (stmt) | yes |  | Apache-2.0 | v2.0.0 (changed after pub.) |  |
| https://github.com/tensorflow/tensorflow | github/code (stmt) (cited tool) | yes |  | Apache-2.0 | v2.4.3, v2.3.4, v2.6.0, v2.5.1, v2.6.0-rc2, v2.6.0-rc1, v2.6.0-rc0, v2.4.2, v2.2.3, v2.1.4 (changed after pub.) |  |
| https://github.com/deepmind/sonnet | github/code (stmt) (cited tool) | yes |  | Apache-2.0 | v2.0.0, v2.0-beta (changed after pub.) |  |
| https://github.com/google/jax/ | github/code (stmt) (cited tool) | yes |  | Apache-2.0 |  (changed after pub.) |  |
| https://github.com/deepmind/dm-haiku | github/code (stmt) (cited tool) | yes |  | Apache-2.0 | v0.0.4, v0.0.3, v0.0.2, v0.0.1, v0.0.1-beta, v0.0.1-alpha (changed after pub.) |  |
| https://github.com/soedinglab/hh-suite | github/code (stmt) (cited tool) | yes |  | GPL-3.0 | userguide, v3.3.0, v3.2.0, v3.1.0, v3.0-beta.3, v3.0-beta.2, v3.0-beta.1 (changed after pub.) |  |
| https://github.com/openmm/openmm | github/code (stmt) (cited tool) | yes |  |  | 7.6.0beta, 7.5.1, 7.5.0, 7.4.2, 7.4.1, 7.4.0, 7.3.1, 7.3.0, 7.2.2, 7.2.1 (changed after pub.) |  |
| https://github.com/soedinglab/MMseqs2 | github/code (stmt) (cited tool) | yes |  | MIT | 13-45111, 12-113e3, 11-e1a1c, 10-6d92c, 9-d36de, 8-fac81, 7-4e23d, 6-f5a1c, 5-9375b, 4-0b8cc (changed after pub.) |  |
| https://github.com/refresh-bio/FAMSA | github/code (stmt) (cited tool) | yes |  | GPL-3.0 | v1.6.2, v1.6.1, v1.5.12-stable, v1.3.2, v1.2.5, v1.2.4, v.1.2.2, v1.2.1, v1.2, v1.1 (changed after pub.) |  |
| https://github.com/numpy/numpy | github/code (stmt) (cited tool) | yes |  | NOASSERTION | v1.21.1, v1.21.0, v1.21.0rc2, v1.21.0rc1, v1.20.3, v1.20.2, v1.20.1, v1.20.0, v1.19.5, v1.20.0rc2 (changed after pub.) | license file present but not recognised by GitHub |
| https://github.com/mwaskom/seaborn | github/code (stmt) (cited tool) | yes |  | BSD-3-Clause | v0.11.2.rc0, joss_paper, v0.11.1, v0.11.0, v0.11.0.rc0, v0.10.1, v0.10.0, v0.9.1, v0.10.0.rc0, v0.9.1.rc0 (changed after pub.) |  |
| https://github.com/matplotlib/matplotlib | github/code (stmt) (cited tool) | yes |  |  | v3.4.3, v3.4.2, v3.4.1, v3.4.0, v3.4.0rc3, v3.4.0rc2, v3.4.0rc1, v3.3.4, v3.3.3, v3.3.2 (changed after pub.) |  |
| https://github.com/bokeh/bokeh | github/code (stmt) (cited tool) | yes |  | BSD-3-Clause |  (changed after pub.) | 100 git tag(s), no GitHub releases |
| https://github.com/pandas-dev/pandas | github/code (stmt) (cited tool) | yes |  | BSD-3-Clause | v1.3.1, v1.3.0, v1.2.5, v1.3.0rc1, v1.2.4, v1.2.3, v1.2.2, v1.2.1, v1.2.0, v1.2.0rc0 (changed after pub.) |  |
| https://github.com/has2k1/plotnine | github/code (stmt) (cited tool) | yes |  | MIT | v0.8.0, v0.7.1, v0.7.0, v0.6.0, v0.5.1, v0.5.0, v0.4.0, v0.3.0, v0.2.0, v0.1.0 (changed after pub.) |  |
| https://cdn.rcsb.org/resources/sequence/clusters/bc-40.out | pdb/data (stmt) | **no** (404) |  |  |  |  |
| https://ftp.ebi.ac.uk/pub/databases/uniprot/previous_releases/release-2020_01/uniref/ | ebi/data (stmt) | yes |  |  |  |  |
| https://ftp.ebi.ac.uk/pub/databases/metagenomics/peptide_database/2018_12/ | ebi/data (stmt) | yes |  |  |  |  |
| http://eddylab.org/software/hmmer/ | other/other (stmt) | ? (403) |  |  |  |  |
| https://www.python.org/ | other/other (stmt) | yes |  |  |  |  |
| https://www.scipy.org/ | other/other (stmt) | yes |  |  |  |  |
| https://www.wwpdb.org/ftp/pdb-ftp-sites | other/other (stmt) | yes |  |  |  |  |
| https://ftp.wwpdb.org/pub/pdb/derived_data/ | other/other (stmt) | **no** (0) |  |  |  | ConnectionError: HTTPSConnectionPool(host='ftp.wwpdb.org', port=443): Max retries exceeded with url: /pub/pdb/derived_da |
| https://wwwuser.gwdg.de/~compbiol/data/hhsuite/databases/hhsuite_dbs/ | other/other (stmt) | yes |  |  |  |  |
| http://doi.org/10.2210/pdb6Y4F/pdb | doi/doi (stmt) | yes |  |  |  |  |
| http://doi.org/10.2210/pdb6YJ1/pdb | doi/doi (stmt) | yes |  |  |  |  |
| http://doi.org/10.2210/pdb6VR4/pdb | doi/doi (stmt) | yes |  |  |  |  |
| http://doi.org/10.2210/pdb6SK0/pdb | doi/doi (stmt) | yes |  |  |  |  |
| http://doi.org/10.2210/pdb6FES/pdb | doi/doi (stmt) | yes |  |  |  |  |
| http://doi.org/10.2210/pdb6W6W/pdb | doi/doi (stmt) | yes |  |  |  |  |

## Repo check: https://github.com/google-deepmind/alphafold

- ✅ `dependency_file`: docker/Dockerfile, docker/requirements.txt, pyproject.toml, requirements.txt
- ✅ `readme`: README.md (35362 chars)
- ✅ `readme_run_steps`: 9 command line(s), usage section
- ✅ `entry_point`: alphafold/model/config.py, config.py, docker/run_docker.py, download_all_data.sh, run_docker.py
- ✅ `license_file`: LICENSE

<sub>paper-repro-auditor 0.1.0 · 2026-11-02T18:11:57+00:00</sub>
