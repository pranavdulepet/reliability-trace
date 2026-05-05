import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.reliability_graph.verifier import DEFAULT_CACHE_DIR, DEFAULT_MODEL_FILE, DEFAULT_NLI_REPO


def parse_args():
    parser = argparse.ArgumentParser(description="Download the required NLI verifier model files.")
    parser.add_argument("--repo", default=DEFAULT_NLI_REPO)
    parser.add_argument("--model-file", default=DEFAULT_MODEL_FILE)
    parser.add_argument("--output-dir", default=str(DEFAULT_CACHE_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from huggingface_hub import hf_hub_download
    except Exception as exc:
        print("huggingface_hub is required. Install project dependencies first: %s" % exc)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = [args.model_file, "tokenizer.json", "config.json"]
    for filename in files:
        source = Path(hf_hub_download(repo_id=args.repo, filename=filename))
        target = output_dir / ("model.onnx" if filename.endswith(".onnx") else Path(filename).name)
        shutil.copyfile(source, target)
        print("saved %s" % target)
    print("NLI verifier files are ready in %s" % output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
