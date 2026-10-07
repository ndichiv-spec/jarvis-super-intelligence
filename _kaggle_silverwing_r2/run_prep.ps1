# run_prep.ps1 - prepare the Silverwing-120M OWT corpus for Kaggle.
#
# SW_HF_TOKEN is NEVER hardcoded here. Supply it via the environment (or a
# project-local .env) before invoking:
#
#   $env:SW_HF_TOKEN = "<hf_...>"
#   powershell -ExecutionPolicy Bypass -File run_prep.ps1
#
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:SW_HF_TOKEN)) {
    throw "[run_prep] SW_HF_TOKEN is not set. Export a Hugging Face write token in the environment first. Refusing to continue without a credential."
}
Write-Output "[run_prep] SW_HF_TOKEN resolved from environment (value not logged)"

$env:SW_HF_CORPUS_REPO="Reyvic-254/silverwing-120m-corpus-v1"
$env:HF_HOME="F:\AI\_kaggle_silverwing_r2\corpus_build\.hf"
python "F:\AI\_kaggle_silverwing_r2\prep\owt_prep.py" --tokens 400000000 --val-tokens 8000000 --sample-chars 260000000 --out "F:\AI\_kaggle_silverwing_r2\corpus_build\corpus"