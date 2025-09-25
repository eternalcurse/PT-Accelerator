# PT-Accelerator v2.0.0

一个面向PT站点用户的全自动加速与管理平台，集成Cloudflare IP优选、PT Tracker批量管理、GitHub/TMDB等站点加速、下载器一键导入、Web可视化配置等多种功能，支持Docker一键部署，适合所有对网络加速和PT站点体验有高要求的用户。

---

## 功能亮点

- **Cloudflare IP优选**：集成CloudflareSpeedTest，自动定时优选全球最快Cloudflare IP，极大提升PT站点和GitHub等访问速度。
- **架构自适应支持**：完美支持AMD64和ARM64架构，自动检测并选择对应的CloudflareSpeedTest可执行文件和配置文件。
- **PT Tracker批量管理**：支持批量添加、批量清空、批量导入、单个删除、状态切换等操作，Tracker管理极致高效。
- **下载器一键导入**：支持qBittorrent、Transmission等主流下载器，自动导入Tracker列表并智能筛选Cloudflare站点。
- **Hosts源多路合并**：内置多条GitHub/TMDB等Hosts源，自动合并、去重、优选，提升全局访问体验。
- **Web可视化配置**：所有操作均可在现代化Web界面完成，支持定时任务、白名单、日志、配置等全方位管理。
- **用户登录认证**：内置用户登录与鉴权机制，保障平台访问安全。
- **多下载器实例支持**：支持同时连接和管理多个qBittorrent及Transmission下载器实例，集中控制更便捷。
- **一键清空/重建**：支持一键清空所有Tracker、清空并重建hosts文件，彻底解决历史污染和遗留问题。
- **日志与状态监控**：内置系统日志、任务进度、调度器状态等实时监控，方便排查和优化。
- **多架构Docker镜像**：提供AMD64和ARM64架构的Docker镜像，支持树莓派、ARM服务器等设备。
- **CI/CD自动化**：集成GitHub Actions，支持自动构建和手动自定义版本发布。
- **多通知渠道**：支持多种通知方式，及时获取系统状态和任务完成通知。
- **Hosts文件编辑**：支持在线编辑Hosts文件，实时预览和保存修改。
- **日志管理**：支持清空日志功能，保持系统日志整洁。
- **移动端适配**：完美适配移动端显示，支持手机和平板设备访问。
- **Hosts结构保护**：修复清空Hosts功能，保护系统原有Hosts文件头结构。
- **极致兼容性**：支持Docker、原生Python环境，支持Linux/Windows/Mac，适配多种部署场景。

---

## 快速开始

### 1. Docker一键部署

推荐使用Docker，简单高效，支持多架构：

```bash
# 自动选择架构（推荐）
docker run -d \
  --name pt-accelerator \
  --network host \
  -v /etc/hosts:/etc/hosts \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  eternalcurse/pt-accelerator:latest

# 指定架构（ARM64架构）
docker run -d \
  --name pt-accelerator \
  --network host \
  -v /etc/hosts:/etc/hosts \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  eternalcurse/pt-accelerator:arm64
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
      - TZ=Asia/Shanghai
    volumes:
      - /etc/hosts:/etc/hosts
      - ./config:/app/config
      - ./logs:/app/logs
```

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
- 一键清空Hosts并重建（彻底清理历史污染，保护系统原有结构）
- 监控IP优选和Hosts更新任务进度
- 支持移动端响应式显示，完美适配手机和平板设备

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
- 支持一键清空日志功能，保持系统整洁

### 6. Hosts文件管理
- 支持在线编辑Hosts文件，实时预览修改效果
- 保护系统原有Hosts文件头结构，避免破坏系统配置
- 智能合并多个Hosts源，自动去重和优化

### 7. 通知系统
- 支持多种通知渠道，及时获取系统状态
- 任务完成通知、错误告警通知
- 可选配置通知方式

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
- **架构自适应**：自动检测系统架构（AMD64/ARM64），选择对应的可执行文件和配置文件
- 相关参数和测速数据文件（ip.txt/ipv6.txt）可在对应架构目录下自定义：
  - AMD64架构：`cfst_linux_amd64/` 目录
  - ARM64架构：`cfst_linux_arm64/` 目录
- 自动筛选延迟低、速度快的优质CF节点IP
- 支持IPv4/IPv6双协议测速
- Docker构建时自动排除不需要的架构文件，优化镜像大小
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

- **Q: 支持哪些架构？**  
  A: 支持AMD64和ARM64架构，包括x86_64服务器、树莓派、ARM服务器等。Docker会自动选择对应架构的镜像。

- **Q: 如何在树莓派上运行？**  
  A: 树莓派使用ARM64架构，直接使用`docker pull eternalcurse/pt-accelerator:latest`即可，Docker会自动选择ARM64版本。

- **Q: 如何手动构建特定版本的镜像？**  
  A: 在GitHub Actions页面可以手动触发构建，并自定义版本号（如v1.0.0-hotfix），支持紧急修复版本发布。

- **Q: 支持哪些通知方式？**  
  A: 支持多种通知渠道，包括系统内置通知、邮件通知等，可在配置中设置通知方式和频率。

- **Q: 如何在线编辑Hosts文件？**  
  A: 在Web界面的Hosts管理模块中，可以直接编辑Hosts文件内容，支持实时预览和保存修改。

- **Q: 清空Hosts会破坏系统配置吗？**  
  A: 不会。系统会保护原有的Hosts文件头结构，只清理PT-Accelerator添加的内容，确保系统配置完整。

- **Q: 支持手机访问吗？**  
  A: 完全支持。Web界面已完美适配移动端，支持手机和平板设备访问，提供良好的移动端体验。

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
- cfst（已内置二进制，支持Linux AMD64/ARM64平台）
- Docker（支持多架构构建和部署）

---

## 参考项目

- [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest) - 优质Cloudflare IP测速工具
- [GitHub Hosts](https://gitlab.com/ineo6/hosts) - 优质GitHub加速hosts源

---

## 版本更新日志

### 最新版本 (v2.0.0)

- ✅ **架构自适应支持**：完美支持AMD64和ARM64架构，自动检测并选择对应的CloudflareSpeedTest文件
- ✅ **Docker构建优化**：优化Dockerfile，支持架构自适应构建，减小镜像大小
- ✅ **CI/CD自动化**：集成GitHub Actions，支持自动构建和手动自定义版本发布
- ✅ **多架构镜像**：提供AMD64和ARM64架构的Docker镜像，支持树莓派等ARM设备
- ✅ **文件管理优化**：添加.gitignore规则，优化版本控制
- ✅ **多通知渠道**：支持多种通知方式，及时获取系统状态和任务完成通知
- ✅ **Hosts文件编辑**：支持在线编辑Hosts文件，实时预览和保存修改
- ✅ **日志管理**：支持清空日志功能，保持系统日志整洁
- ✅ **移动端适配**：完美适配移动端显示，支持手机和平板设备访问
- ✅ **Hosts结构保护**：修复清空Hosts功能，保护系统原有Hosts文件头结构
- ✅ **版本显示**：Web界面显示当前版本号，便于版本管理

### 版本历史

- **v2.0.0** (2025-09-25) - 架构自适应支持、多通知渠道、移动端适配、Hosts结构保护
- **v1.0.0** (2025-04-29) - 初始版本发布

### 主要功能

- ✅ **Cloudflare IP优选**：自动定时优选全球最快Cloudflare IP
- ✅ **PT Tracker管理**：批量管理PT站点Tracker
- ✅ **下载器集成**：支持qBittorrent、Transmission等主流下载器
- ✅ **Hosts源管理**：多路合并GitHub/TMDB等Hosts源
- ✅ **Web界面**：现代化Web界面，支持实时配置和监控

---

## 许可证

MIT License

---

如有问题、建议或需求，欢迎在GitHub Issue区反馈！ 
