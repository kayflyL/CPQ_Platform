# -*- coding: utf-8 -*-
"""泛化校验：既有 5 案例 + 4 个新需求变体，走 /api/reasoning-flow/test-run。"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api/reasoning-flow/test-run"

CASES = [
    ("C1-A800x2", "机箱：4U 机架式（含8个全高全长双宽PCIe5.0 GPU卡位，支持12个3.5英寸硬盘：前置8盘位SATA+4盘位NVMe U.2，2700W 2+2/3+1冗余高效铂金电源）\nCPU：AMD EPYC 9654 96核192线程 2.4GHz L3 384MB TDP 360W *2\n内存：64GB DDR5 4800MHz R-ECC *24\n硬盘：SATA SSD PM893A 1.92T（组建RAID 1）*2\n硬盘：U.2 NVMe PM9A3 3.84T（组建RAID 5）*4\nRAID卡：LSI 9560 16i 8G缓存（用于NVMe U.2组建阵列）*1\nRAID卡：LSI 9364 8i 2G缓存（用于前置8盘位机械硬盘组建阵列）*1\n网卡：双口万兆 X710DA2BLK 光口含模块 *1\nGPU：NVIDIA A800 80G *2"),
    ("C2-RTX4500", "2* AMD EPYC™ 9254 24  2.9 GHz 128 MB 200W\n2* 32G DDR5\n1* 960G NMVE\n1 *RTX PRO 4500 Server 32G\n1 *双口万兆\n2* 1300W冗余电源"),
    ("C3-RAID-level", "机箱：2U机架式服务器\nCPU：AMD 9124 26C/32T 3.0GHz *2\n内存：DDR5 32G*4\n硬盘：SATA SSD 480G*2\n硬盘：U.2 NVME 7.68T*4\n阵列卡：RAID 0,1,10 *1\n网卡：千兆4口 *1\n网卡：25G 双口 含光模块 *1\n网卡：100G 双口 含光模块 *1"),
    ("C4-64G5600", "机箱：2U 机架式机箱、双冗余铂金电源、原厂导轨、内部线材、散热组件 *1\nCPU：AMD Genoa 9554, 3.1GHz/64 物理核 / 256MB 缓存 / 360W, CTO&BTO 标准模块 *2\n内存：64GB DDR5-5600B RDIMM 服务器内存 *24\n系统固态硬盘：960GB 企业级 SSD, 2.5 寸热插拔 (含光模块) *2\n网卡模块：10G 万兆以太网网卡, PCIe4.0 适配 (含光模块) *3\nRAID 阵列卡：LSI 9560-8i 12Gb SAS RAID 卡, 8 个 SAS 口、4GB 缓存、PCIe4.0, 不含超级电容, CTO&BTO 模块 *1"),
    ("C5-32G4800", "机箱：2U机架式\nCPU：AMD 9654 * 2\n内存：DDR5  32 * 16\n硬盘：SATA SSD 960G * 2\n硬盘：U.2 NVME 7.68T * 2\nRAID卡：9560-8I * 1\n网卡：CX5 25G 双口 含光模块 * 2\n电源：根据功耗选择"),
    ("N1-A100x8", "4U AI训练服务器：8张全高全长双宽GPU卡位；CPU AMD EPYC 9654×2；内存 128G DDR5 5600 R-ECC×12；硬盘 1.92T SATA SSD×2 + 7.68T U.2 NVMe×4；RAID卡 LSI 9560-16i×1；GPU NVIDIA A100 80G×8；网卡 双口25G 含光模块×2"),
    ("N2-9334", "2U通用计算服务器；CPU AMD EPYC 9334×2；内存 32G DDR5 4800×8；硬盘 480G SATA SSD×2；RAID卡 9540-8i×1；网卡 25G双口 含光模块×1"),
    ("N3-storage", "4U存储服务器；CPU Intel Xeon 6430×2；硬盘 16T SATA HDD×16；系统盘 960G SATA SSD×2；RAID卡 LSI 9560-16i×1；网卡 10G双口 含光模块×2"),
    ("N4-singleGPU", "单路GPU工作站；CPU AMD EPYC 9124×1；GPU NVIDIA RTX 5000 Ada 32G×4；内存 64G DDR5 4800×4；硬盘 2T NVMe SSD×1；网卡 10G双口 含光模块×1"),
]


def post(text):
    data = json.dumps({"requirement_text": text, "force_complete": True}).encode("utf-8")
    req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def flat_parts(resp):
    parts = []
    for k, v in (resp.get("kp_by_model") or {}).items():
        if isinstance(v, list):
            parts.extend(v)
    return parts


def main():
    only = set(sys.argv[1:])
    for label, text in CASES:
        if only and label not in only:
            continue
        print(f"RUN {label}", flush=True)
        t0 = time.time()
        try:
            resp = post(text)
            dur = round(time.time() - t0, 1)
            ext = resp.get("ext") or {}
            plans = resp.get("plans") or []
            model = (plans[0].get("name") if plans else "") or ""
            parts = flat_parts(resp)
            unmatched = [p for p in parts if p.get("unmatched")]
            mismatch = [p for p in parts if p.get("spec_mismatch")]
            print(f"\n=== {label} | {dur}s | model={model} | type={ext.get('server_type_name')} form={ext.get('form')} series={ext.get('series')} ===")
            node_durs = [(e.get("step"), e.get("duration_ms")) for e in (resp.get("events") or []) if e.get("type") == "step_done"]
            if node_durs:
                print("  node_ms:", " ".join(f"{s}={ms}" for s, ms in node_durs))
            print(f"  error={resp.get('error') or ''} fatal={resp.get('fatal') or ''} awaiting={resp.get('awaiting_input')}")
            for p in parts:
                flag = "UNMATCH" if p.get("unmatched") else ("MISMATCH" if p.get("spec_mismatch") else "ok")
                extra = p.get("unmatched_reason") or p.get("request_spec") or ""
                print(f"  [{flag}] {p.get('category')} | {p.get('pn')} | req={p.get('request_spec') or ''} got={p.get('grounded_spec') or ''} | {extra}")
            print(f"  unmatched={len(unmatched)} spec_mismatch={len(mismatch)} parts={len(parts)}")
        except Exception as e:
            print(f"\n=== {label} ERROR {round(time.time()-t0,1)}s ===")
            print("  ", repr(e))
        time.sleep(4)


if __name__ == "__main__":
    main()
