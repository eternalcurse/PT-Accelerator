# PT-Accelerator

一个面向PT站点用户的全自动加速与管理平台，集成Cloudflare IP优选、PT Tracker批量管理、GitHub/TMDB等站点加速、下载器一键导入、Web可视化配置等多种功能，支持Docker一键部署，适合所有对网络加速和PT站点体验有高要求的用户。

---

## 功能亮点

- **Cloudflare IP优选**：集成CloudflareSpeedTest，自动定时优选全球最快Cloudflare IP，极大提升PT站点和GitHub等访问速度。
- **PT Tracker批量管理**：支持批量添加、批量清空、批量导入、单个删除、状态切换等操作，Tracker管理极致高效。
- **下载器一键导入**：支持qBittorrent、Transmission等主流下载器，自动导入Tracker列表并智能筛选Cloudflare站点。
- **Hosts源多路合并**：内置多条GitHub/TMDB等Hosts源，自动合并、去重、优选，提升全局访问体验。
- **Web可视化配置**：所有操作均可在现代化Web界面完成，支持定时任务、白名单、日志、配置等全方位管理。
- **用户登录认证**：内置用户登录与鉴权机制，保障平台访问安全。
- **多下载器实例支持**：支持同时连接和管理多个qBittorrent及Transmission下载器实例，集中控制更便捷。
- **一键清空/重建**：支持一键清空所有Tracker、清空并重建hosts文件，彻底解决历史污染和遗留问题。
- **日志与状态监控**：内置系统日志、任务进度、调度器状态等实时监控，方便排查和优化。
- **极致兼容性**：支持Docker、原生Python环境，支持Linux/Windows/Mac，适配多种部署场景。

---

## 快速开始

### 1. Docker一键部署

推荐使用Docker，简单高效：

```bash
docker run -d \
  --name pt-accelerator \
  --network host \
  -v /etc/hosts:/etc/hosts \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  -e APP_PORT=23333 \
  eternalcurse/pt-accelerator:latest
```

或使用`docker-compose.yml`：

```yaml
services:
  pt-accelerator:
    image: eternalcurse/pt-accelerator:latest
    container_name: pt-accelerator
    restart: unless-stopped
    network_mode: host
    environment:
      TZ: "${TZ:-Asia/Shanghai}"
      APP_PORT: "${APP_PORT:-23333}"
    volumes:
      - /etc/hosts:/etc/hosts
      - ./config:/app/config
      - ./logs:/app/logs
```

如需自定义时区或端口，可复制 `.env.example` 为 `.env` 后修改对应变量。

创建上述`docker-compose.yml`文件后，在同一目录下运行：

```bash
docker-compose up -d
```

### 2. 本地运行（开发/调试）

```bash
# 克隆仓库
git clone https://github.com/eternalcurse/PT-Accelerator.git
cd PT-Accelerator

# 安装依赖
pip install -r requirements.txt

# 启动服务
bash start.sh
# 或
python -m uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-23333}
```
---

## Web界面入口

- 访问：http://your-ip:<端口号>
- 首次访问或根据配置，可能需要进行用户登录。
- 默认端口：`23333`。可以通过以下方式修改：
  - **Docker/Docker Compose**:
    - 在 `docker-compose.yml` 文件中，为 `pt-accelerator` 服务的 `environment` 部分添加或修改 `APP_PORT` 的值。例如:
      ```yaml
      services:
        pt-accelerator:
          # ... other settings ...
          environment:
            - TZ=Asia/Shanghai
            - APP_PORT=8080 # 设置自定义端口
      ```
    - 或者，在 `docker-compose.yml` 同级目录下创建 `.env` 文件并写入 `APP_PORT=8080`，这会覆盖 `docker-compose.yml` 中的默认设置（如果存在）。
  - **本地运行**: 启动前设置 `APP_PORT` 环境变量 (例如 `export APP_PORT=8080 && bash start.sh`)，或者直接修改 `start.sh` 脚本中的默认端口。
- 支持多用户同时操作，所有配置实时生效

---

## 主要功能模块

### 1. 控制面板
- 查看调度器状态、定时任务、快速运行IP优选与Hosts更新
- 一键仅更新Hosts
- 一键清空Hosts并重建（彻底清理历史污染）
- 监控IP优选和Hosts更新任务进度

### 2. Tracker管理
- 批量添加、批量清空、单个删除、状态切换
- 一键导入下载器Tracker（自动筛选Cloudflare站点）
- 支持Cloudflare白名单管理
- Tracker IP一键批量更新
- 支持大量PT站点Tracker自动配置

### 3. Hosts源管理
- 支持多条外部Hosts源，自动合并、去重、优选
- 支持添加、删除、启用/禁用Hosts源
- 内置多个优质Hosts源（GitHub和TMDB加速）
- 自动定时更新所有Hosts源

### 4. 下载器管理
- 支持添加和管理**多个**qBittorrent、Transmission等主流下载器实例，每个实例均可独立配置。
- 一键测试连接、保存配置、导入Tracker
- 支持端口、用户名密码、HTTPS等完整配置
- 自动验证连接有效性

### 5. 日志与监控
- 实时查看系统日志、操作日志、任务进度
- 支持刷新、自动滚动
- 记录所有关键操作和错误信息

---

## 配置文件说明（config/config.yaml）

- `auth`：用户认证配置 (新增)
  - `enable`：是否启用用户认证 (例如 `true` 或 `false`)
  - `username`：登录用户名
  - `password`：登录密码 (建议存储哈希后的密码，具体请参照您的实现方式)

- `cloudflare`：Cloudflare优选相关配置
  - `enable`：是否启用Cloudflare IP优选
  - `cron`：定时任务Cron表达式（默认每天0点）
  - `ipv6`：是否启用IPv6测速
  - `additional_args`：CloudflareST额外参数
  - `notify`：是否开启通知
  
- `cloudflare_domains`：Cloudflare白名单域名列表（需要优化的域名）

- `hosts_sources`：外部Hosts源列表
  - `name`：源名称
  - `url`：源URL地址
  - `enable`：是否启用

- `torrent_clients`：下载器配置列表 (支持多个实例)
  - 每个下载器实例为一个列表项，包含以下字段：
    - `name`: (必填) 用户为此下载器实例设定的唯一名称 (例如 `qb-main`, `tr-backup`)
    - `type`: (必填) 下载器类型，可选值为 `qbittorrent` 或 `transmission`
    - `host`：下载器主机地址
    - `port`：下载器端口
    - `username`/`password`：登录凭据
    - `use_https`：是否使用HTTPS (例如 `true` 或 `false`)
    - `enable`：是否启用此下载器实例 (例如 `true` 或 `false`)
  - 示例:
    ```yaml
    torrent_clients:
      - name: qBittorrent主服务器
        type: qbittorrent
        host: localhost
        port: 8080
        username: admin
        password: adminadmin
        use_https: false
        enable: true
      - name: Transmission备用
        type: transmission
        host: 192.168.1.100
        port: 9091
        username: 
        password: 
        use_https: false
        enable: true
    ```

- `trackers`：PT站点Tracker列表
  - `name`：Tracker名称
  - `domain`：Tracker域名
  - `ip`：优选的IP地址
  - `enable`：是否启用

**所有配置均可通过Web界面实时修改，无需手动编辑。**

---

## CloudflareSpeedTest说明

- 已内置CloudflareST二进制和测速脚本，自动调用，无需手动操作
- 相关参数和测速数据文件（ip.txt/ipv6.txt）可在`CloudflareST_linux_amd64`目录下自定义
- 自动筛选延迟低、速度快的优质CF节点IP
- 支持IPv4/IPv6双协议测速
- 参考：https://github.com/XIU2/CloudflareSpeedTest

---

## 常见问题

- **Q: 为什么要挂载/etc/hosts？**  
  A: 程序会自动优化和重写系统hosts文件，提升全局访问速度，必须有写入权限。

- **Q: 如何彻底清空tracker或hosts？**  
  A: Web界面提供"一键清空所有tracker""清空hosts并重建"按钮，安全高效。

- **Q: 支持哪些PT站点？**  
  A: 支持所有基于Cloudflare的PT站点，非Cloudflare站点会自动过滤。

- **Q: 日志和配置如何持久化？**  
  A: 建议挂载`/app/config`和`/app/logs`到本地目录，防止容器重启丢失数据。

- **Q: 如果系统使用了代理，会影响IP测速吗？**  
  A: 会影响。建议在测速时临时关闭系统代理，确保获得准确的测速结果。

- **Q: 项目如何更新？**  
  A: 使用Docker部署的用户可以通过`docker pull eternalcurse/pt-accelerator:latest`拉取最新镜像，再重新创建容器。

- **Q: 如何让Docker容器化的下载器（如qBittorrent）使用优化后的hosts？**  
  A: 在下载器的Docker配置中，添加挂载`/etc/hosts:/etc/hosts:ro`（只读模式），示例：
  ```yaml
  services:
    qbittorrent:
      image: linuxserver/qbittorrent
      # ... 其他配置 ...
      volumes:
        - /etc/hosts:/etc/hosts:ro  # 挂载hosts文件为只读
        - ./config:/config
        - ./downloads:/downloads
  ```
  注意：无论使用什么网络模式（host、bridge等），都需要显式挂载hosts文件，容器不会自动使用宿主机的hosts文件。当PT-Accelerator更新宿主机hosts文件时，容器内的hosts文件也会自动同步更新。

---

## 依赖与环境

- Python 3.9+
- FastAPI、Uvicorn、APScheduler、requests、jinja2
- python-hosts、transmission-rpc、dnspython等（详见requirements.txt）
- CloudflareST（已内置二进制，支持Linux平台）

---

## 参考项目

- [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest) - 优质Cloudflare IP测速工具
- [GitHub Hosts](https://gitlab.com/ineo6/hosts) - 优质GitHub加速hosts源

---

## 许可证

MIT License

---

如有问题、建议或需求，欢迎在GitHub Issue区反馈！ 
