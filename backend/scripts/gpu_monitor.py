import subprocess
import csv
import time
import os
from datetime import datetime

def get_gpu_metrics():
    try:
        # Run nvidia-smi command to query memory used, total, and GPU utilization
        cmd = [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits"
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        # Parse output: e.g. "1240, 4096, 12"
        parts = [p.strip() for p in result.stdout.strip().split(",")]
        if len(parts) >= 3:
            memory_used = int(parts[0])
            memory_total = int(parts[1])
            utilization = int(parts[2])
            return memory_used, memory_total, utilization
    except Exception as e:
        print(f"Error querying nvidia-smi: {e}")
    return None

def main():
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, "gpu_metrics.csv")
    
    print(f"Starting GPU monitor...")
    print(f"Logging to: {csv_path}")
    print("Press Ctrl+C to stop.")
    
    # Write header if file doesn't exist
    file_exists = os.path.exists(csv_path)
    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "memory_used_mib", "memory_total_mib", "utilization_percent"])
            f.flush()
            
        try:
            while True:
                metrics = get_gpu_metrics()
                if metrics:
                    memory_used, memory_total, utilization = metrics
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow([timestamp, memory_used, memory_total, utilization])
                    f.flush()
                    print(f"[{timestamp}] Memory: {memory_used}/{memory_total} MiB | GPU Util: {utilization}%")
                else:
                    print("Failed to fetch GPU metrics. Retrying...")
                time.sleep(2.0)
        except KeyboardInterrupt:
            print("\nStopping GPU monitor. Goodbye.")

if __name__ == "__main__":
    main()
