# Alpasim

## 0. 현재 setup된 Alpasim-DDS
```bash
# 4090, DGX 둘다 해당 디렉토리에 위치
~/Workspace/gr/alpasim

# DGX에서 driver를 먼저 실행
cd ~/Workspace/gr/alpasim/run_driver_only
docker compose --profile sim up driver-0

# 이후 4090에서 sim 실행
cd ~/Workspace/gr/alpasim/run_distributed
docker compose --profile sim up runtime-0 controller-0 physics-0 sensorsim-0
```

시뮬레이션 결과는 `~/Workspace/gr/alpasim/run_distributed/rollouts/clipgt-{scene_id}/{rollout_id}/` 하위에 저장된다.

```
run_distributed/rollouts/
└── clipgt-{scene_id}/
    └── {rollout_id}/
        ├── rollout.asl                          # ASL 로그
        ├── metrics.parquet                      # 메트릭 데이터
        └── *_reasoning_overlay.mp4              # REASONING_OVERLAY 비디오
```

아래는 초기 setup 과정이다. 위 환경에서 이미 setup이 완료되었으므로 위의 환경에서 진행한다면 아래 과정을 거치지 않아도 된다.

<br>

## 1. Alpasim 서버 설정 (4090, x86_64)

```bash
git clone https://github.com/IntellectusCorp/alpasim.git
cd alpasim  # $ALPASIM_WORKDIR

# main 브랜치 사용 (기본)

# alpasim_wizard 사용 전 local env setup
source setup_local_env.sh

# Wizard로 설정 생성
uv run alpasim_wizard +deploy=local \
    wizard.log_dir=$PWD/run_distributed \
    wizard.run_method=NONE \
    wizard.debug_flags.use_localhost=True \
    driver=[ar1,ar1_runtime_configs]
```

설정 파일이 자동으로 생성된다.

<br>

## 2. Alpamayo 드라이버 서버 설정 (Dell Pro Max GB10, ARM)

```bash
git clone https://github.com/IntellectusCorp/alpasim.git
cd alpasim  # $ALPASIM_WORKDIR

# aarch 브랜치로 전환 (ARM 빌드용)
git checkout aarch
```

<br>

### ARM용 wheel 설치

`point_cloud_utils`는 ARM용 PyPI wheel이 없으므로, 사전 빌드된 wheel을 프로젝트 루트에서 설치해야 한다.
Alpasim 4090 서버(x86_64)의 원본 프로젝트에 wheel 파일이 포함되어 있다.
이 wheel은 `aarch` 브랜치의 `pyproject.toml` 또는 `Dockerfile`에서 자동 참조된다.

```bash
scp 192.168.0.5:~/Workspace/alpasim/point_cloud_utils-0.35.0-cp312-cp312-linux_aarch64.whl .
```

<br>

### 설정파일 생성

```bash
uv run alpasim_wizard +deploy=local \
    wizard.log_dir=$PWD/run_driver_only \
    wizard.run_method=NONE \
    wizard.debug_flags.use_localhost=True \
    driver=[ar1,ar1_runtime_configs]
```

`run_driver_only/driver-config.yaml` 주요 설정:
- Alpasim 서버의 `run_distributed/driver-config.yaml`과 **use_cameras 설정이 동일**해야 함

```yaml
inference:
  context_length: 4
  max_batch_size: 1
  subsample_factor: 1
  use_cameras:
    - camera_cross_left_120fov
    - camera_front_wide_120fov
    - camera_cross_right_120fov
    - camera_front_tele_30fov
```

<br>

## 3. 시뮬레이션 실행

Docker Compose를 사용하며, 이미지가 빌드되어 있지 않으면 자동으로 빌드 후 시작한다.
이미지 태그는 docker-compose.yaml에서 직접 설정한다.

### 실행 순서 (반드시 드라이버 먼저)

**Step 1) GB10에서 Alpamayo 드라이버 실행:**

```bash
cd $ALPASIM_WORKDIR/run_driver_only
docker compose --profile sim up driver-0
```

**Step 2) 4090에서 Alpasim 시뮬레이션 실행:**

```bash
cd $ALPASIM_WORKDIR/run_distributed
docker compose --profile sim up runtime-0 controller-0 physics-0 sensorsim-0
```

평가(eval)와 aggregation은 runtime-0이 종료될 때 자동으로 실행된다.

