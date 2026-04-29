import sys
import argparse
import uvicorn

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from app.config import get_base_url, PORT


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tunnel", action="store_true", help="通过 ngrok 创建公网隧道")
    args = parser.parse_args()

    port = PORT
    display_url = get_base_url()

    if args.tunnel:
        try:
            from pyngrok import ngrok
            tunnel = ngrok.connect(port)
            public_url = tunnel.public_url
            import os
            os.environ["BASE_URL"] = public_url
            # Also update config module since it was already imported
            import app.config as _config
            _config.BASE_URL = public_url
            display_url = public_url
            print(f"\n  🌐 公网地址（ngrok）：{public_url}")
        except ImportError:
            print("  ⚠️  pyngrok 未安装，使用局域网模式 (pip install pyngrok)")
        except Exception as e:
            print(f"  ⚠️  ngrok 启动失败：{e}，使用局域网模式")

    print("\n" + "=" * 50)
    print(f"  今天吃什么 🍜")
    print(f"  访问地址：{display_url}")
    print("=" * 50)

    mode = "公网（ngrok）" if args.tunnel else "局域网"
    print(f"\n  模式：{mode}\n")

    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
