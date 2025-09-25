document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM fully loaded and parsed');
    // 加载初始数据
    loadDashboard();
    loadCloudflareConfig();
    loadTrackers();
    loadHostsSources();
    loadLogs();
    loadCurrentHosts();
    loadCustomAcceleratedSites();
    // 绑定事件
    bindEvents();
    enhanceInputValidation();
    // 初始化通知设置功能
    initNotifySettings();
});

function bindEvents() {
    // 下载器管理初始化已移至torrent_clients.js的DOMContentLoaded事件中，避免重复初始化
    // 运行CloudflareSpeedTest按钮事件
    const btnRunCloudflare = document.getElementById('btn-run-cloudflare');
    if (btnRunCloudflare) {
        btnRunCloudflare.addEventListener('click', function() {
            this.disabled = true;
            const spinner = document.createElement('div');
            spinner.className = 'spinner-container';
            spinner.innerHTML = '<div class="spinner-border spinner-border-sm text-light" role="status"><span class="visually-hidden">Loading...</span></div>';
            this.appendChild(spinner);
            fetch('/api/run-cfst-script', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    showActionResult(data.message, 'success');
                    loadCurrentHosts();
                    setTimeout(() => {
                        fetch('/api/task-status')
                            .then(res => res.json())
                            .then(res => {
                                if (res.status === 'done') {
                                    loadCurrentHosts();
                                    showToast('Hosts已自动更新', 'success');
                                }
                            });
                    }, 3000);
                })
                .catch(error => {
                    console.error('运行IP优选与Hosts更新任务失败:', error);
                    showActionResult('运行IP优选与Hosts更新任务失败', 'danger');
                })
                .finally(() => {
                    this.disabled = false;
                    this.removeChild(spinner);
                });
        });
    }
    // 更新Hosts
    const btnUpdateHosts = document.getElementById('btn-update-hosts');
    if (btnUpdateHosts) {
        btnUpdateHosts.addEventListener('click', function() {
            const resultElement = document.getElementById('action-result');
            resultElement.innerHTML = '<div class="alert alert-info">正在更新Hosts...</div>';
            fetch('/api/update-hosts', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    resultElement.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
                    loadCurrentHosts();
                    setTimeout(() => { resultElement.innerHTML = ''; }, 5000);
                })
                .catch(error => {
                    console.error('更新Hosts失败:', error);
                    resultElement.innerHTML = '<div class="alert alert-danger">更新Hosts失败</div>';
                });
        });
    }
    // 保存Cloudflare配置
    const cloudflareForm = document.getElementById('cloudflare-form');
    if (cloudflareForm) {
        cloudflareForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const saveBtn = document.getElementById('save-cloudflare-btn');
            const spinner = document.getElementById('cloudflare-spinner');
            const resultSpan = document.getElementById('cloudflare-save-result');
            if (saveBtn) saveBtn.disabled = true;
            if (spinner) spinner.classList.remove('d-none');
            if (resultSpan) resultSpan.textContent = '';
            const config = {
                cloudflare: {
                    enable: document.getElementById('cloudflare-enable').checked,
                    cron: document.getElementById('cloudflare-cron').value
                }
            };
            fetch('/api/config')
                .then(response => response.json())
                .then(fullConfig => {
                    const updatedConfig = { ...fullConfig, cloudflare: config.cloudflare };
                    return fetch('/api/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(updatedConfig)
                    });
                })
                .then(response => response.json())
                .then(() => {
                    showToast('定时任务配置已保存', 'success');
                    if (resultSpan) {
                        resultSpan.textContent = '保存成功';
                        resultSpan.className = 'ms-2 text-success';
                        setTimeout(() => { resultSpan.textContent = ''; }, 3000);
                    }
                    loadDashboard();
                })
                .catch(error => {
                    console.error('保存配置失败:', error);
                    showToast('保存定时任务配置失败: ' + error.message, 'danger');
                    if (resultSpan) {
                        resultSpan.textContent = '保存失败';
                        resultSpan.className = 'ms-2 text-danger';
                    }
                })
                .finally(() => {
                    if (saveBtn) saveBtn.disabled = false;
                    if (spinner) spinner.classList.add('d-none');
                });
        });
    }
    // 添加Tracker
    const saveTrackerBtn = document.getElementById('save-tracker');
    if (saveTrackerBtn) {
        saveTrackerBtn.addEventListener('click', function() {
            const name = document.getElementById('tracker-name').value;
            const domain = document.getElementById('tracker-domain').value;
            const enable = document.getElementById('tracker-enable').checked;
            const forceCloudflare = document.getElementById('tracker-force-cloudflare') ? document.getElementById('tracker-force-cloudflare').checked : false;
            if (!name || !domain) {
                showToast('请填写完整信息', 'warning', 8000);
                return;
            }
            const tracker = { name, domain, enable, ip: '' };
            this.disabled = true;
            const originalText = this.textContent;
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 处理中...';
            showToast('正在添加Tracker，请稍候...', 'info', 8000);
            fetch(`/api/trackers?force_cloudflare=${forceCloudflare}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(tracker)
            })
                .then(response => response.json())
                .then(data => {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addTrackerModal'));
                    if (modal) modal.hide();
                    document.getElementById('add-tracker-form').reset();
                    loadTrackers();
                    showToast(data.message || 'Tracker已添加', 'success');
                })
                .catch(error => {
                    console.error('添加Tracker失败:', error);
                    showToast(error.message, 'danger', 10000);
                })
                .finally(() => {
                    this.disabled = false;
                    this.innerHTML = originalText;
                });
        });
    }
    // 添加Hosts源
    const saveHostsSourceBtn = document.getElementById('save-hosts-source');
    if (saveHostsSourceBtn) {
        saveHostsSourceBtn.addEventListener('click', function() {
            const name = document.getElementById('hosts-source-name').value;
            const url = document.getElementById('hosts-source-url').value;
            const enable = document.getElementById('hosts-source-enable').checked;
            if (!name || !url) {
                showToast('请填写完整信息', 'warning', 8000);
                return;
            }
            const source = { name, url, enable };
            fetch('/api/hosts-sources', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(source)
            })
                .then(response => response.json())
                .then(data => {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addHostsSourceModal'));
                    if (modal) modal.hide();
                    document.getElementById('add-hosts-source-form').reset();
                    loadHostsSources();
                    loadCurrentHosts();
                    showToast('Hosts源已添加', 'success');
                })
                .catch(error => {
                    console.error('添加Hosts源失败:', error);
                    showToast(error.message, 'danger', 10000);
                });
        });
    }
    // 刷新日志
    const refreshLogsBtn = document.getElementById('refresh-logs');
    if (refreshLogsBtn) {
        refreshLogsBtn.addEventListener('click', function() { loadLogs(); });
    }
    // 清空日志
    const clearLogsBtn = document.getElementById('clear-logs');
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener('click', function() {
            showConfirmModal('确认操作', '确定要清空系统日志吗？此操作不可恢复。', function onConfirm() {
                clearLogsBtn.disabled = true;
                fetch('/api/logs/clear', { method: 'POST' })
                    .then(res => res.json())
                    .then(res => {
                        if (res && res.success) {
                            showToast(res.message || '日志已清空', 'success');
                            const logsElement = document.getElementById('logs');
                            logsElement.textContent = '';
                            // 成功清空后自动刷新一次最新日志
                            loadLogs();
                        } else {
                            showToast((res && res.message) || '清空日志失败', 'danger');
                        }
                    })
                    .catch(err => {
                        console.error('清空日志失败:', err);
                        showToast('清空日志失败: ' + err.message, 'danger');
                    })
                    .finally(() => {
                        clearLogsBtn.disabled = false;
                    });
            });
        });
    }
    // 批量添加Tracker
    const saveBatchTrackersBtn = document.getElementById('save-batch-trackers');
    if (saveBatchTrackersBtn) {
        saveBatchTrackersBtn.addEventListener('click', function() {
            const domainsText = document.getElementById('tracker-domains').value;
            if (!domainsText.trim()) {
                showToast('请输入至少一个域名', 'warning', 8000);
                return;
            }
            const domains = domainsText.split('\n').map(d => d.trim()).filter(d => d);
            if (domains.length === 0) {
                showToast('请输入至少一个有效域名', 'warning', 8000);
                return;
            }
            batchAddTrackers(domains);
        });
    }
    // 运行优选脚本按钮
    const btnRunCfstScript = document.getElementById('btn-run-cfst-script');
    if (btnRunCfstScript) {
        btnRunCfstScript.addEventListener('click', function() { runCfstScript(); });
    }
    // 批量更新IP按钮
    const btnUpdateAllTrackers = document.getElementById('btn-update-all-trackers');
    if (btnUpdateAllTrackers) {
        btnUpdateAllTrackers.addEventListener('click', function() {
            const ip = document.getElementById('batch-update-ip').value.trim();
            if (!ip) {
                showToast('请输入有效的IP地址', 'warning', 8000);
                return;
            }
            const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
            if (!ipv4Regex.test(ip)) {
                showToast('请输入有效的IPv4地址，格式如：104.16.91.215', 'warning', 8000);
                return;
            }
            updateAllTrackersIp(ip);
        });
    }
    // 清空hosts并更新按钮
    const btnClearAndUpdateHosts = document.getElementById('btn-clear-and-update-hosts');
    if (btnClearAndUpdateHosts) {
        btnClearAndUpdateHosts.addEventListener('click', function() {
            showConfirmModal('确认操作', '确定要清理由本项目写入的 hosts 分区并重新生成吗？此操作不会清空您原有的 hosts 内容。建议先备份。', function onConfirm() {
                btnClearAndUpdateHosts.disabled = true;
                showToast('正在执行清理并更新hosts，请稍候...', 'info', 10000);
                fetch('/api/clear-and-update-hosts', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        showToast(data.message || '已清理项目分区并更新hosts', 'success', 10000);
                        loadCurrentHosts();
                    })
                    .catch(error => {
                        showToast('清理并更新hosts失败: ' + error.message, 'danger', 10000);
                    })
                    .finally(() => {
                        btnClearAndUpdateHosts.disabled = false;
                    });
            });
        });
    }
    // Hosts编辑按钮
    const btnEditHosts = document.getElementById('btn-edit-hosts');
    if (btnEditHosts) {
        btnEditHosts.addEventListener('click', function() {
            showConfirmModal('确认操作', '此操作将修改系统Hosts文件，如果你不知道接下来该干什么请取消！', function onConfirm() {
                // 打开编辑模态框并加载当前内容
                fetch('/api/current-hosts')
                    .then(res => res.json())
                    .then(data => {
                        const content = Array.isArray(data.hosts) ? data.hosts.join('') : (data.hosts || '');
                        const textarea = document.getElementById('edit-hosts-textarea');
                        textarea.value = content;
                        const modal = new bootstrap.Modal(document.getElementById('editHostsModal'));
                        modal.show();
                    })
                    .catch(err => {
                        showToast('加载当前hosts失败: ' + err.message, 'danger');
                    });
            });
        });
    }
    // 保存Hosts
    const saveHostsBtn = document.getElementById('save-hosts-btn');
    if (saveHostsBtn) {
        saveHostsBtn.addEventListener('click', function() {
            const textarea = document.getElementById('edit-hosts-textarea');
            const content = textarea.value;
            saveHostsBtn.disabled = true;
            fetch('/api/save-hosts-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            })
            .then(res => res.json())
            .then(res => {
                if (res && res.success) {
                    showToast(res.message || 'Hosts已保存', 'success');
                    loadCurrentHosts();
                    const modalEl = document.getElementById('editHostsModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                } else {
                    showToast((res && res.message) || '保存失败', 'danger');
                }
            })
            .catch(err => {
                showToast('保存失败: ' + err.message, 'danger');
            })
            .finally(() => {
                saveHostsBtn.disabled = false;
            });
        });
    }
    // 清空所有tracker按钮
    const btnClearAllTrackers = document.getElementById('btn-clear-all-trackers');
    if (btnClearAllTrackers) {
        btnClearAllTrackers.addEventListener('click', function() {
            showConfirmModal('确认操作', '确定要清空所有tracker吗？此操作不可恢复，建议先备份。', function onConfirm() {
                btnClearAllTrackers.disabled = true;
                showToast('正在清空所有tracker，请稍候...', 'info', 10000);
                fetch('/api/clear-all-trackers', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        showToast(data.message || '已清空所有tracker', 'success', 10000);
                        loadTrackers();
                        loadCurrentHosts();
                    })
                    .catch(error => {
                        showToast('清空所有tracker失败: ' + error.message, 'danger', 10000);
                    })
                    .finally(() => {
                        btnClearAllTrackers.disabled = false;
                    });
            });
        });
    }
    // ----- 自定义站点加速功能相关事件绑定 -----
    const addCustomSiteBtn = document.getElementById('add-custom-site-btn');
    if (addCustomSiteBtn) {
        addCustomSiteBtn.addEventListener('click', addCustomAcceleratedSite);
    }

    const refreshCustomSitesBtn = document.getElementById('refresh-custom-sites-btn');
    if (refreshCustomSitesBtn) {
        refreshCustomSitesBtn.addEventListener('click', loadCustomAcceleratedSites);
    }

    // 监听自定义站点加速选项卡的显示事件
    const customSitesTab = document.getElementById('custom-sites-tab');
    if (customSitesTab) {
        customSitesTab.addEventListener('shown.bs.tab', function (event) {
            loadCustomAcceleratedSites();
        });
    }
    // ----- 自定义站点加速功能相关事件绑定 END -----
}

// 加载控制面板数据
function loadDashboard() {
    console.log('Loading dashboard data'); // 添加日志
    // 获取调度器状态
    fetch('/api/scheduler-status')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('scheduler-status');
            const statusBadgeElement = document.getElementById('scheduler-status-badge');
            const jobsElement = document.getElementById('scheduler-jobs');
            
            if (data.running) {
                statusElement.innerHTML = '<span class="text-success">运行中</span>';
                if (statusBadgeElement) {
                    statusBadgeElement.textContent = '运行中';
                    statusBadgeElement.className = 'status-badge badge-running';
                }
            } else {
                statusElement.innerHTML = '<span class="text-danger">已停止</span>';
                if (statusBadgeElement) {
                    statusBadgeElement.textContent = '已停止';
                    statusBadgeElement.className = 'status-badge badge-stopped';
                }
            }
            
            // 清空任务列表
            jobsElement.innerHTML = '';
            
            // 添加任务
            if (data.jobs && data.jobs.length > 0) {
                data.jobs.forEach(job => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${job.name}</td>
                        <td>${job.next_run}</td>
                    `;
                    jobsElement.appendChild(row);
                });
            } else {
                jobsElement.innerHTML = '<tr><td colspan="2">暂无定时任务</td></tr>';
            }
        })
        .catch(error => {
            console.error('获取调度器状态失败:', error);
            document.getElementById('scheduler-status').innerHTML = 
                '<span class="text-danger">获取状态失败</span>';
            
            const statusBadgeElement = document.getElementById('scheduler-status-badge');
            if (statusBadgeElement) {
                statusBadgeElement.textContent = '获取失败';
                statusBadgeElement.className = 'status-badge badge-stopped';
            }
        });
}

// 加载Cloudflare配置
function loadCloudflareConfig() {
    console.log('Loading Cloudflare config'); // 添加日志
    fetch('/api/config')
        .then(response => response.json())
        .then(config => {
            const cloudflareConfig = config.cloudflare || {};
            
            // 设置表单值
            document.getElementById('cloudflare-enable').checked = 
                cloudflareConfig.enable !== undefined ? cloudflareConfig.enable : true;
            document.getElementById('cloudflare-cron').value = 
                cloudflareConfig.cron || '0 0 * * *';
        })
        .catch(error => {
            console.error('加载定时任务配置失败:', error);
            showToast('加载定时任务配置失败', 'danger', 10000);
        });
}

// 加载Trackers
function loadTrackers() {
    fetch('/api/config')
        .then(response => response.json())
        .then(config => {
            const trackers = config.trackers || [];
            const tableElement = document.getElementById('trackers-table');
            
            // 清空表格
            tableElement.innerHTML = '';
            
            // 添加Trackers
            if (trackers.length > 0) {
                trackers.forEach(tracker => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${tracker.name || ''}</td>
                        <td>${tracker.domain || ''}</td>
                        <td>${tracker.ip || '未设置'}</td>
                        <td>
                            <div class="form-check form-switch">
                                <input class="form-check-input tracker-switch" type="checkbox" 
                                    data-domain="${tracker.domain}" 
                                    ${tracker.enable === true ? 'checked' : ''}>
                            </div>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-danger delete-tracker" 
                                data-domain="${tracker.domain}">
                                <i class="bi bi-trash"></i> 删除
                            </button>
                        </td>
                    `;
                    tableElement.appendChild(row);
                });
                
                // 绑定Tracker开关事件
                document.querySelectorAll('.tracker-switch').forEach(switchElement => {
                    switchElement.addEventListener('change', function() {
                        const domain = this.getAttribute('data-domain');
                        const enable = this.checked;
                        
                        updateTracker(domain, { enable });
                    });
                });
                
                // 绑定删除Tracker事件
                document.querySelectorAll('.delete-tracker').forEach(button => {
                    button.addEventListener('click', function() {
                        const domain = this.getAttribute('data-domain');
                        
                        if (confirm(`确定要删除Tracker "${domain}" 吗？`)) {
                            deleteTracker(domain);
                        }
                    });
                });
            } else {
                tableElement.innerHTML = '<tr><td colspan="5" class="text-center">暂无Tracker</td></tr>';
            }
        })
        .catch(error => {
            console.error('加载Trackers失败:', error);
            showToast('加载Trackers失败', 'danger', 10000);
        });
}

// 加载Hosts源
function loadHostsSources() {
    fetch('/api/config')
        .then(response => response.json())
        .then(config => {
            const sources = config.hosts_sources || [];
            const tableElement = document.getElementById('hosts-sources-table');
            
            // 清空表格
            tableElement.innerHTML = '';
            
            // 添加Hosts源
            if (sources.length > 0) {
                sources.forEach(source => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${source.name || ''}</td>
                        <td>${source.url || ''}</td>
                        <td>
                            <div class="form-check form-switch">
                                <input class="form-check-input hosts-source-switch" type="checkbox" 
                                    data-url="${source.url}" 
                                    ${source.enable ? 'checked' : ''}>
                            </div>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-danger delete-hosts-source" 
                                data-url="${source.url}">
                                <i class="bi bi-trash"></i> 删除
                            </button>
                        </td>
                    `;
                    tableElement.appendChild(row);
                });
                
                // 绑定Hosts源开关事件
                document.querySelectorAll('.hosts-source-switch').forEach(switchElement => {
                    switchElement.addEventListener('change', function() {
                        const url = this.getAttribute('data-url');
                        const enable = this.checked;
                        
                        updateHostsSource(url, { enable });
                    });
                });
                
                // 绑定删除Hosts源事件
                document.querySelectorAll('.delete-hosts-source').forEach(button => {
                    button.addEventListener('click', function() {
                        const url = this.getAttribute('data-url');
                        
                        if (confirm(`确定要删除Hosts源 "${url}" 吗？`)) {
                            deleteHostsSource(url);
                        }
                    });
                });
            } else {
                tableElement.innerHTML = '<tr><td colspan="4" class="text-center">暂无Hosts源</td></tr>';
            }
        })
        .catch(error => {
            console.error('加载Hosts源失败:', error);
            showToast('加载Hosts源失败', 'danger', 10000);
        });
}

// 加载日志
function loadLogs() {
    fetch('/api/logs')
        .then(response => response.json())
        .then(data => {
            const logsElement = document.getElementById('logs');
            // 适配后端返回的带换行字符串
            if (typeof data.logs === 'string' && data.logs.length > 0) {
                logsElement.textContent = data.logs;
                logsElement.scrollTop = logsElement.scrollHeight;
            } else if (Array.isArray(data.logs) && data.logs.length > 0) {
                logsElement.textContent = data.logs.join('');
                logsElement.scrollTop = logsElement.scrollHeight;
            } else {
                logsElement.textContent = '暂无日志';
            }
        })
        .catch(error => {
            console.error('加载日志失败:', error);
            document.getElementById('logs').textContent = '加载日志失败';
        });
}

// 加载当前Hosts文件
function loadCurrentHosts() {
    fetch('/api/current-hosts')
        .then(response => response.json())
        .then(data => {
            const hostsElement = document.getElementById('current-hosts');
            
            if (data.hosts && data.hosts.length > 0) {
                hostsElement.textContent = data.hosts.join('');
            } else {
                hostsElement.textContent = '获取hosts文件失败';
            }
        })
        .catch(error => {
            console.error('获取hosts文件失败:', error);
            document.getElementById('current-hosts').textContent = '获取hosts文件失败';
        });
}

// 更新Tracker
function updateTracker(domain, data) {
    fetch('/api/config')
        .then(response => response.json())
        .then(config => {
            // 查找并更新Tracker
            const trackers = config.trackers || [];
            let updated = false;
            
            for (let i = 0; i < trackers.length; i++) {
                if (trackers[i].domain === domain) {
                    trackers[i] = { ...trackers[i], ...data };
                    updated = true;
                    break;
                }
            }
            
            if (!updated) {
                showToast('未找到指定的Tracker', 'warning', 8000);
                return;
            }
            
            // 保存配置
            return fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });
        })
        .then(response => response.json())
        .then(data => {
            showToast('Tracker已更新', 'success');
            
            // 刷新Hosts文件
            loadCurrentHosts();
        })
        .catch(error => {
            console.error('更新Tracker失败:', error);
            showToast('更新Tracker失败', 'danger', 10000);
        });
}

// 删除Tracker
function deleteTracker(domain) {
    fetch(`/api/trackers/${domain}`, {
        method: 'DELETE'
    })
        .then(response => {
            if (response.ok) {
                return response.json();
            } else {
                return response.json().then(data => {
                    throw new Error(data.detail || '删除Tracker失败');
                });
            }
        })
        .then(data => {
            showToast('Tracker已删除', 'success');
            
            // 刷新Trackers列表
            loadTrackers();
            
            // 刷新Hosts文件
            loadCurrentHosts();
        })
        .catch(error => {
            console.error('删除Tracker失败:', error);
            showToast(error.message, 'danger', 10000);
        });
}

// 更新Hosts源
function updateHostsSource(url, data) {
    showToast('正在更新Hosts源，请稍候...', 'info', 8000);
    fetch('/api/config')
        .then(response => response.json())
        .then(config => {
            // 查找并更新Hosts源
            const sources = config.hosts_sources || [];
            let updated = false;
            
            for (let i = 0; i < sources.length; i++) {
                if (sources[i].url === url) {
                    sources[i] = { ...sources[i], ...data };
                    updated = true;
                    break;
                }
            }
            
            if (!updated) {
                showToast('未找到指定的Hosts源', 'warning', 8000);
                return;
            }
            
            // 保存配置
            return fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });
        })
        .then(response => response.json())
        .then(data => {
            showToast('Hosts源已更新', 'success');
            
            // 刷新Hosts文件
            loadCurrentHosts();
        })
        .catch(error => {
            console.error('更新Hosts源失败:', error);
            showToast('更新Hosts源失败', 'danger', 10000);
        });
}

// 删除Hosts源
function deleteHostsSource(url) {
    showToast('正在删除Hosts源，请稍候...', 'info', 8000);
    fetch(`/api/hosts-sources?url=${encodeURIComponent(url)}`, {
        method: 'DELETE'
    })
        .then(response => {
            if (response.ok) {
                return response.json();
            } else {
                return response.json().then(data => {
                    throw new Error(data.detail || '删除Hosts源失败');
                });
            }
        })
        .then(data => {
            showToast('Hosts源已删除', 'success');
            loadHostsSources();
            loadCurrentHosts();
        })
        .catch(error => {
            console.error('删除Hosts源失败:', error);
            showToast(error.message, 'danger', 10000);
        });
}

// 只保留一份showToast实现，放在文件底部，所有调用都用此函数
function showToast(message, type = 'info', delay = 8000) {
    console.log('显示Toast:', message, type);
    
    // 确保 delay 参数是数字类型
    if (typeof delay !== 'number') {
        delay = parseInt(delay, 10) || 8000;
    }
    
    // 如果已有相同内容的Toast，先关闭它
    const existingToasts = document.querySelectorAll('.toast');
    existingToasts.forEach(toast => {
        const toastBody = toast.querySelector('.toast-body');
        if (toastBody && toastBody.textContent.trim() === message) {
            const bsToast = bootstrap.Toast.getInstance(toast);
            if (bsToast) {
                bsToast.hide();
            }
        }
    });
    // 创建Toast元素
    const toastElement = document.createElement('div');
    toastElement.className = `toast align-items-center text-white bg-${type} border-0`;
    toastElement.setAttribute('role', 'alert');
    toastElement.setAttribute('aria-live', 'assertive');
    toastElement.setAttribute('aria-atomic', 'true');
    toastElement.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    // 添加到页面
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    toastContainer.appendChild(toastElement);
    // 显示Toast
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: delay
    });
    // 悬停时不消失
    let paused = false;
    let remaining = delay;
    let hideTimeout;
    toastElement.addEventListener('mouseenter', function() {
        paused = true;
        toast._config.autohide = false;
        clearTimeout(hideTimeout);
    });
    toastElement.addEventListener('mouseleave', function() {
        paused = false;
        toast._config.autohide = true;
        hideTimeout = setTimeout(() => toast.hide(), remaining);
    });
    // 记录显示时间，支持悬停恢复
    toastElement.addEventListener('shown.bs.toast', function() {
        const start = Date.now();
        hideTimeout = setTimeout(() => {
            if (!paused) toast.hide();
        }, remaining);
        toastElement.addEventListener('mouseenter', function() {
            remaining -= Date.now() - start;
        }, { once: true });
    });
    toast.show();
    // Toast隐藏后移除元素
    toastElement.addEventListener('hidden.bs.toast', function() {
        if (toastContainer.children.length <= 1) {
            document.body.removeChild(toastContainer);
        } else {
            toastContainer.removeChild(toastElement);
        }
    });
}

// 通用确认模态框
function showConfirmModal(title, message, onConfirm) {
    const titleEl = document.getElementById('confirmModalLabel');
    const messageEl = document.getElementById('confirmMessage');
    const okBtn = document.getElementById('confirmOkBtn');
    const modalEl = document.getElementById('confirmModal');
    if (!titleEl || !messageEl || !okBtn || !modalEl) {
        if (confirm(message)) {
            typeof onConfirm === 'function' && onConfirm();
        }
        return;
    }
    titleEl.textContent = title || '确认操作';
    messageEl.textContent = message || '确定要执行此操作吗？';
    const modal = new bootstrap.Modal(modalEl);

    // 确保不会累积旧的确认回调（取消时旧回调不会被触发也应被移除）
    if (window.__confirmOkHandler) {
        try { okBtn.removeEventListener('click', window.__confirmOkHandler); } catch (e) {}
        window.__confirmOkHandler = null;
    }

    const handler = () => {
        modal.hide();
        try { okBtn.removeEventListener('click', handler); } catch (e) {}
        window.__confirmOkHandler = null;
        typeof onConfirm === 'function' && onConfirm();
    };
    okBtn.addEventListener('click', handler);
    window.__confirmOkHandler = handler;

    // 关闭/取消时也清理handler，避免下一次残留触发
    const cleanup = () => {
        if (window.__confirmOkHandler) {
            try { okBtn.removeEventListener('click', window.__confirmOkHandler); } catch (e) {}
            window.__confirmOkHandler = null;
        }
        modalEl.removeEventListener('hidden.bs.modal', cleanup);
    };
    modalEl.addEventListener('hidden.bs.modal', cleanup);
    modal.show();
}

// fetchWithTimeout工具函数，支持超时
function fetchWithTimeout(resource, options = {}, timeout = 180000) {
    return Promise.race([
        fetch(resource, options),
        new Promise((_, reject) => setTimeout(() => reject(new Error('导入任务已提交，处理时间较长请耐心等待，稍后可刷新页面查看结果')), timeout))
    ]);
}

// 批量添加Trackers
function batchAddTrackers(domains, forceCloudflare = false) {
    showToast('正在批量添加域名...', 'info', 8000);
    fetch('/api/batch-add-domains', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ domains })
    })
    .then(response => response.json())
    .then(async data => {
        // 新增：如forceCloudflare为true，批量写入白名单
        if (forceCloudflare && Array.isArray(domains)) {
            for (const d of domains) {
                await fetch(`/api/cloudflare-domains?domain=${encodeURIComponent(d)}`, { method: 'POST' });
            }
        }
        const status = data.status || (data.message.includes('成功') ? 'success' : 'warning');
        showToast(data.message || '批量添加域名操作已完成', status, 8000);
        if (data.filtered_domains && data.filtered_domains.length > 0) {
            showToast('以下域名未检测到Cloudflare特征，已被跳过：' + data.filtered_domains.join(', '), 'warning', 8000);
        }
        if (data.details) {
            console.log('批量添加域名详情:', data.details);
        }
        const modal = bootstrap.Modal.getInstance(document.getElementById('batchAddTrackerModal'));
        if (modal) {
            modal.hide();
        }
        document.getElementById('tracker-domains').value = '';
        loadTrackers();
        loadCurrentHosts();
    })
    .catch(error => {
        console.error('批量添加域名失败:', error);
        showToast('批量添加域名失败: ' + error.message, 'danger', 10000);
    });
}

// 运行CloudflareSpeedTest优选脚本
function runCfstScript() {
    showToast('正在启动IP优选与Hosts更新任务...', 'info', 8000);
    fetch('/api/run-cfst-script', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(response => response.json())
    .then(data => {
        showToast(data.message || 'IP优选任务已启动', 'success', 8000);
        // 延迟一段时间后，确保IP优选有足够时间完成
        setTimeout(() => {
            // 先调用更新hosts API
            fetch('/api/update-hosts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            .then(res => res.json())
            .then(hostData => {
                showToast(hostData.message || 'Hosts文件已更新', 'success', 8000);
                // 然后刷新界面显示
                loadDashboard();
                loadTrackers(); // 强制刷新Tracker列表，确保IP显示最新
                loadCurrentHosts();
            })
            .catch(error => {
                console.error('更新Hosts失败:', error);
                showToast('更新Hosts失败: ' + error.message, 'danger', 10000);
            });
        }, 5000); // 增加等待时间到5秒，确保IP优选有足够时间完成
    })
    .catch(error => {
        console.error('启动IP优选任务失败:', error);
        showToast('启动IP优选任务失败: ' + error.message, 'danger', 10000);
    });
}

// 批量更新所有Tracker的IP
function updateAllTrackersIp(ip) {
    showToast('正在更新所有Tracker的IP...', 'info', 8000);
    
    fetch(`/api/update-all-trackers?ip=${encodeURIComponent(ip)}`, {
        method: 'POST'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('更新所有Tracker的IP失败');
        }
        return response.json();
    })
    .then(data => {
        showToast(data.message || `已将所有Tracker的IP更新为 ${ip}`, 'success', 8000);
        
        // 重新加载Tracker列表
        loadTrackers();
        
        // 更新hosts文件显示
        loadCurrentHosts();
    })
    .catch(error => {
        console.error('更新所有Tracker的IP失败:', error);
        showToast('更新所有Tracker的IP失败: ' + error.message, 'danger', 10000);
    });
}

// 显示操作结果
function showActionResult(message, type = 'info') {
    const resultElement = document.getElementById('action-result');
    if (!resultElement) return;
    
    resultElement.innerHTML = `<div class="alert alert-${type} mt-3">${message}</div>`;
    
    // 5秒后自动清除
    setTimeout(() => {
        resultElement.innerHTML = '';
    }, 5000);
}

// 显示进度模态框
function showProgressModal(message) {
    // 显示进度弹窗
    $("#progressModal").modal({
        backdrop: 'static',
        keyboard: false
    });
    $("#progressModal").modal("show");
    
    // 设置消息
    $("#progress-message").text(message || "请稍候，操作正在进行中...");
    
    // 返回一个轮询函数，可以用于检查任务状态
    return function pollTaskStatus(callback) {
        let intervalId = setInterval(function() {
            $.ajax({
                url: "/api/task-status",
                type: "GET",
                success: function(response) {
                    console.log('Task status response:', response);
                    
                    // 更新进度信息
                    if (response.message) {
                        $("#progress-message").text(response.message);
                    }
                    
                    // 如果任务完成，停止轮询并执行回调
                    if (response.status === "done") {
                        clearInterval(intervalId);
                        hideProgressModal();
                        if (typeof callback === 'function') {
                            callback(response);
                        }
                    }
                },
                error: function(xhr, status, error) {
                    console.error('Poll task status failed:', status, error);
                    // 出错时也停止轮询
                    clearInterval(intervalId);
                    hideProgressModal();
                    showToast("查询任务状态失败: " + error, "danger");
                }
            });
        }, 2000); // 每2秒查询一次
        
        // 返回计时器ID，以便在需要时手动清除
        return intervalId;
    };
}

function hideProgressModal() {
    $("#progressModal").modal("hide");
}

// ========== 前端输入校验增强 ========== //

function enhanceInputValidation() {
    // CRON表达式校验
    const cronInput = document.getElementById('cloudflare-cron');
    if (cronInput) {
        cronInput.addEventListener('input', function() {
            const value = cronInput.value.trim();
            const resultSpan = document.getElementById('cloudflare-save-result');
            if (!isValidCron(value)) {
                resultSpan.textContent = 'CRON格式无效，需5段数字/星号/逗号/横线';
                resultSpan.className = 'ms-2 text-danger';
            } else {
                resultSpan.textContent = '';
            }
        });
    }
    // hosts源URL校验和自动补全
    const hostsUrlInput = document.getElementById('hosts-source-url');
    if (hostsUrlInput) {
        hostsUrlInput.addEventListener('blur', function() {
            let value = hostsUrlInput.value.trim();
            if (value && !/^https?:\/\//i.test(value)) {
                value = 'https://' + value;
                hostsUrlInput.value = value;
            }
            if (!isValidUrl(value)) {
                hostsUrlInput.classList.add('is-invalid');
            } else {
                hostsUrlInput.classList.remove('is-invalid');
            }
        });
    }
    // 下载器主机和端口校验
    const qbHost = document.getElementById('qbittorrent-host');
    const qbPort = document.getElementById('qbittorrent-port');
    const trHost = document.getElementById('transmission-host');
    const trPort = document.getElementById('transmission-port');
    [qbHost, trHost].forEach(input => {
        if (input) {
            input.addEventListener('blur', function() {
                if (!isValidHost(input.value.trim())) {
                    input.classList.add('is-invalid');
                } else {
                    input.classList.remove('is-invalid');
                }
            });
        }
    });
    [qbPort, trPort].forEach(input => {
        if (input) {
            input.addEventListener('blur', function() {
                if (!isValidPort(input.value.trim())) {
                    input.classList.add('is-invalid');
                } else {
                    input.classList.remove('is-invalid');
                }
            });
        }
    });
}

function isValidCron(str) {
    // 简单校验：5段，允许数字、*、,、-、/，不做复杂语义校验
    return /^([\d\*\/,\-]+\s+){4}[\d\*\/,\-]+$/.test(str);
}
function isValidUrl(url) {
    try {
        new URL(url);
        return true;
    } catch {
        return false;
    }
}
function isValidHost(host) {
    // 简单校验IP或域名
    return /^(?:[a-zA-Z0-9\-\.]+|\d{1,3}(?:\.\d{1,3}){3})$/.test(host);
}
function isValidPort(port) {
    const n = Number(port);
    return Number.isInteger(n) && n >= 1 && n <= 65535;
}

// ===== Cloudflare白名单管理UI =====
window.loadCloudflareDomains = function() {
    fetch('/api/cloudflare-domains')
        .then(res => res.json())
        .then(data => {
            const list = data.cloudflare_domains || [];
            const container = document.getElementById('cloudflare-domains-list');
            if (!container) return;
            container.innerHTML = '';
            list.forEach(domain => {
                const li = document.createElement('li');
                li.className = 'list-group-item d-flex justify-content-between align-items-center';
                li.innerHTML = `<span>${domain}</span><button class="btn btn-sm btn-danger" onclick="removeCloudflareDomain('${domain}')">移除</button>`;
                container.appendChild(li);
            });
        });
}
window.addCloudflareDomain = function() {
    const input = document.getElementById('cloudflare-domain-input');
    let domain = input.value.trim();
    if (!domain) return;
    // 自动去除http/https前缀和路径，保证与tracker一致
    domain = domain.replace(/^https?:\/\//i, '').split('/')[0];
    fetch(`/api/cloudflare-domains?domain=${encodeURIComponent(domain)}`, { method: 'POST' })
        .then(() => {
            input.value = '';
            loadCloudflareDomains();
            showToast('已添加到Cloudflare白名单', 'success');
        });
}
window.removeCloudflareDomain = function(domain) {
    fetch(`/api/cloudflare-domains?domain=${encodeURIComponent(domain)}`, { method: 'DELETE' })
        .then(() => {
            loadCloudflareDomains();
            showToast('已移除Cloudflare白名单', 'success');
        });
}

// ----- 自定义站点加速功能 ----- 
function loadCustomAcceleratedSites() {
    const listElement = document.getElementById('custom-sites-list');
    const loadingElement = document.getElementById('custom-sites-loading');

    if (!listElement || !loadingElement) return;

    loadingElement.style.display = 'block'; // 显示加载提示
    // 清空现有列表项（除了加载提示）
    while (listElement.firstChild && listElement.firstChild !== loadingElement) {
        listElement.removeChild(listElement.firstChild);
    }
    
    fetch('/api/custom-accelerated-sites')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(sites => {
            loadingElement.style.display = 'none'; // 隐藏加载提示
            listElement.innerHTML = ''; // 彻底清空，包括可能残留的loading
            if (sites.length === 0) {
                listElement.innerHTML = '<li class="list-group-item text-center text-muted p-3">暂无自定义加速站点。</li>';
                return;
            }
            sites.forEach(site => {
                const listItem = document.createElement('li');
                listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
                listItem.textContent = site;

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn btn-danger btn-sm';
                deleteBtn.innerHTML = '<i class="bi bi-trash"></i> 删除';
                deleteBtn.onclick = function() { deleteCustomAcceleratedSite(site); };

                listItem.appendChild(deleteBtn);
                listElement.appendChild(listItem);
            });
        })
        .catch(error => {
            loadingElement.style.display = 'none';
            listElement.innerHTML = '<li class="list-group-item text-center text-danger p-3">加载站点列表失败，请稍后重试。</li>';
            console.error('加载自定义加速站点列表失败:', error);
            showToast('加载自定义站点列表失败: ' + error.message, 'danger');
        });
}

function addCustomAcceleratedSite() {
    const domainInput = document.getElementById('custom-site-domain-input');
    const feedbackElement = document.getElementById('add-custom-site-feedback');
    const domain = domainInput.value.trim();

    if (!domain) {
        showToast('请输入要加速的站点域名', 'warning');
        domainInput.classList.add('is-invalid');
        if (feedbackElement) feedbackElement.innerHTML = '<div class="text-danger">域名不能为空。</div>';
        return;
    }
    // 简单的域名格式校验
    const domainRegex = /^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}$/;
    if (!domainRegex.test(domain)) {
        showToast('域名格式无效，请输入正确的域名，例如：mysite.example.com', 'warning');
        domainInput.classList.add('is-invalid');
        if (feedbackElement) feedbackElement.innerHTML = '<div class="text-danger">域名格式无效。</div>';
        return;
    }
    domainInput.classList.remove('is-invalid');
    if (feedbackElement) feedbackElement.innerHTML = '';

    const formData = new FormData();
    formData.append('domain', domain);

    const addBtn = document.getElementById('add-custom-site-btn');
    const originalBtnText = addBtn.innerHTML;
    addBtn.disabled = true;
    addBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 添加中...';

    fetch('/api/custom-accelerated-sites', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (response.status === 409) { // Conflict - Domain already exists
            return response.json().then(err => { throw new Error(err.detail || '站点已存在'); });
        }
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
        }
        return response.json();
    })
    .then(data => {
        showSuccessModal('操作成功', data.message || `站点 ${domain} 已成功添加并触发hosts更新。`);
        //showToast(data.message || `站点 ${domain} 已成功添加并触发hosts更新。`, 'success');
        domainInput.value = ''; // 清空输入框
        loadCustomAcceleratedSites(); // 刷新列表
        loadCurrentHosts(); // 更新当前hosts显示
    })
    .catch(error => {
        console.error('添加自定义加速站点失败:', error);
        showErrorModal('添加失败', error.message || '添加站点时发生未知错误。');
        //showToast('添加站点失败: ' + error.message, 'danger');
        domainInput.classList.add('is-invalid');
        if (feedbackElement) feedbackElement.innerHTML = `<div class="text-danger">${error.message}</div>`;
    })
    .finally(() => {
        addBtn.disabled = false;
        addBtn.innerHTML = originalBtnText;
    });
}

function deleteCustomAcceleratedSite(domain) {
    if (!confirm(`确定要删除加速站点 ${domain} 吗？`)) {
        return;
    }
    showProgressModal(`正在删除站点 ${domain}...`);

    fetch(`/api/custom-accelerated-sites/${encodeURIComponent(domain)}`, {
        method: 'DELETE'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
        }
        return response.json();
    })
    .then(data => {
        hideProgressModal();
        showSuccessModal('操作成功', data.message || `站点 ${domain} 已成功删除并触发hosts更新。`);
        //showToast(data.message || `站点 ${domain} 已成功删除并触发hosts更新。`, 'success');
        loadCustomAcceleratedSites(); // 刷新列表
        loadCurrentHosts(); // 更新当前hosts显示
    })
    .catch(error => {
        hideProgressModal();
        console.error(`删除自定义加速站点 ${domain} 失败:`, error);
        showErrorModal('删除失败', error.message || `删除站点 ${domain} 时发生未知错误。`);
        //showToast(`删除站点 ${domain} 失败: ` + error.message, 'danger');
    });
}
// ----- 自定义站点加速功能 END -----

// ===== 通知设置功能 =====

// 初始化通知设置功能
function initNotifySettings() {
    // 加载通知配置
    loadNotifyConfig();
    
    // 绑定事件监听器
    bindNotifyEvents();
}

// 加载通知配置
async function loadNotifyConfig() {
    try {
        const response = await fetch('/api/notify/config');
        const data = await response.json();
        
        if (data.success) {
            const notifyConfig = data.notify || {};
            
            // 更新启用状态
            const notifyEnabled = document.getElementById('notifyEnabled');
            if (notifyEnabled) {
                notifyEnabled.checked = notifyConfig.enable || false;
            }
            // 更新一言开关
            const hitokotoEl = document.getElementById('notifyHitokoto');
            if (hitokotoEl) {
                // 后端默认 True，前端若未配置则置为 true
                const hitokotoVal = (typeof notifyConfig.hitokoto === 'undefined') ? true : !!notifyConfig.hitokoto;
                hitokotoEl.checked = hitokotoVal;
            }
            
            // 加载通知渠道列表
            loadNotifyChannels(notifyConfig.channels || {});
        }
    } catch (error) {
        console.error('加载通知配置失败:', error);
        showToast('加载通知配置失败', 'danger');
    }
}

// 加载通知渠道列表
function loadNotifyChannels(channels) {
    const container = document.getElementById('notifyChannelsList');
    if (!container) return;

    if (!channels || Object.keys(channels).length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-4"><i class="bi bi-bell-slash fs-1"></i><p class="mt-2">暂无通知渠道配置</p></div>';
        return;
    }

    const rows = Object.entries(channels).map(([key, config]) => {
        const type = (config.type || key);
        const typeName = getChannelTypeName(type);
        const enabled = !!config.enable;

        // webhook 专属展示信息 + 每渠道一言标记
        const method = (config.WEBHOOK_METHOD || '').toUpperCase();
        const url = config.WEBHOOK_URL || '';
        const contentType = config.WEBHOOK_CONTENT_TYPE || '';
        const hasBody = !!(config.WEBHOOK_BODY && String(config.WEBHOOK_BODY).trim());
        const hitokotoOn = (typeof config.HITOKOTO !== 'undefined') ? !!config.HITOKOTO : false;

        const methodClass = 'bg-warning text-white';
        const leftBadges = [
            `<span class=\"badge bg-secondary ms-2 me-2\">${typeName}</span>`,
            method ? `<span class=\"badge ${methodClass} me-2\">${method}</span>` : ''
        ]
        .concat(hitokotoOn ? [`<span class=\"badge bg-info text-white me-2\"><i class=\"bi bi-stars\"></i> 一言</span>`] : [])
        .join('');

        const urlLine = url ? `
            <div class=\"small mb-1 text-muted d-flex align-items-start\">\n
            <i class=\"bi bi-link-45deg me-1 flex-shrink-0 mt-1\"></i>\n
            <span class=\"text-break\" style=\"word-break: break-all;\">${url}</span>\n
            </div>` : '';

        const metaLineParts = [];
        if (contentType) {
            metaLineParts.push(`<i class=\"bi bi-file-earmark-code me-1\"></i>${contentType}`);
        }
        if (hasBody) {
            metaLineParts.push(`<i class=\"bi bi-file-earmark-text me-1\"></i>自定义Body`);
        }
        const metaLine = metaLineParts.length ? `<div class="small text-muted">${metaLineParts.join(' <span class=\"mx-1\">|</span> ')}</div>` : '';

        return `
        <div class=\"card mb-3\">\n
        <div class=\"card-body py-3\">\n
        <div class=\"d-flex flex-column flex-md-row align-items-start align-items-md-center justify-content-between\">\n
        <div class=\"flex-grow-1 pe-md-3 mb-2 mb-md-0\">\n
        <div class=\"d-flex flex-wrap align-items-center mb-1\">\n
        <span class=\"fw-semibold me-2\">${config.name || key}</span>\n
        ${leftBadges}\n
        <div class=\"form-check form-switch ms-auto ms-md-1 d-none d-md-block\">\n
        <input class=\"form-check-input\" type=\"checkbox\" ${enabled ? 'checked' : ''} onchange=\"toggleChannel('${key}', this.checked)\">\n
        </div>\n
        </div>\n
        ${urlLine}\n
        ${metaLine}\n
        </div>\n
        <div class=\"d-flex flex-row align-items-center gap-1\">
                        <button class="btn btn-sm btn-outline-secondary d-flex align-items-center text-nowrap" onclick="testSingleChannel('${key}')">
                            <i class="bi bi-send me-1"></i> <span>测试</span>
                        </button>
                        <button class="btn btn-sm btn-outline-warning d-flex align-items-center text-nowrap" onclick="editChannel('${key}')">
                            <i class="bi bi-pencil-square me-1"></i> <span>编辑</span>
                        </button>
                        <button class="btn btn-sm btn-outline-danger d-flex align-items-center text-nowrap" onclick="deleteChannel('${key}')">
                            <i class="bi bi-trash me-1"></i> <span>删除</span>
                        </button>
                        <div class=\"form-check form-switch d-block d-md-none ms-3\">\n
                        <input class=\"form-check-input\" type=\"checkbox\" ${enabled ? 'checked' : ''} onchange=\"toggleChannel('${key}', this.checked)\">\n
                        </div>
                    </div>
                </div>\n
            </div>\n
        </div>`;
    });

    container.innerHTML = rows.join('');
}

// 获取渠道类型名称
function getChannelTypeName(type) {
    const typeNames = {
        'wecom_bot': '企业微信Bot',
        'wecom_app': '企业微信App',
        'telegram': 'Telegram',
        'smtp': '邮件',
        'bark': 'Bark',
        'serverj': 'Server酱',
        'chat': 'Synology Chat',
        'feishu': '飞书机器人',
        'dingding': '钉钉机器人',
        'igot': 'iGot 聚合推送',
        'webhook': '自定义Webhook'
    };
    return typeNames[type] || type;
}

// 绑定通知相关事件
function bindNotifyEvents() {
    // 通知启用开关
    const notifyEnabled = document.getElementById('notifyEnabled');
    if (notifyEnabled) {
        notifyEnabled.addEventListener('change', updateNotifyEnabled);
    }
    // 移除页面级一言开关，改由渠道内配置
    
    // 添加通知渠道按钮（重置为新增模式）
    const addNotifyBtn = document.getElementById('add-notify-channel-btn');
    if (addNotifyBtn) {
        addNotifyBtn.addEventListener('click', openAddNotifyChannelModal);
    }

    // 渠道类型选择器
    const channelType = document.getElementById('channel-type');
    if (channelType) {
        channelType.addEventListener('change', showChannelConfig);
    }
    
    // 保存渠道按钮
    const saveChannelBtn = document.getElementById('save-notify-channel');
    if (saveChannelBtn) {
        saveChannelBtn.addEventListener('click', saveNotifyChannel);
    }
    
    // 全局测试按钮已移除，改为每个渠道卡片上的“测试”按钮
}

// 更新通知启用状态
async function updateNotifyEnabled() {
    const enabled = document.getElementById('notifyEnabled').checked;
    
    try {
        // 先获取现有配置，避免覆盖其它字段
        const current = await fetch('/api/notify/config').then(r => r.json());
        const notifyCfg = (current && current.success && current.notify) ? current.notify : {};
        const merged = {
            ...notifyCfg,
            enable: enabled,
        };
        const response = await fetch('/api/notify/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ notify: merged })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`通知功能已${enabled ? '启用' : '禁用'}`, 'success');
        } else {
            throw new Error(data.message || '更新失败');
        }
    } catch (error) {
        console.error('更新通知状态失败:', error);
        showToast('更新失败: ' + error.message, 'danger');
        // 恢复开关状态
        document.getElementById('notifyEnabled').checked = !enabled;
    }
}

// 显示渠道配置
function showChannelConfig() {
    const type = document.getElementById('channel-type').value;
    const configs = document.querySelectorAll('.channel-config');
    
    // 隐藏所有配置
    configs.forEach(config => {
        config.style.display = 'none';
    });
    
    // 显示对应配置
    if (type) {
        // 处理特殊的ID映射
        let configId = type + '-config';
        if (type === 'wecom_bot') {
            configId = 'wecom-config';
        }
        
        const config = document.getElementById(configId);
        if (config) {
            config.style.display = 'block';
        }
    }
}

// 保存通知渠道
async function saveNotifyChannel() {
    const form = document.getElementById('notify-channel-form');
    const channelData = {
        name: document.getElementById('channel-name').value,
        type: document.getElementById('channel-type').value,
        enable: document.getElementById('channel-enable').checked,
    };
    
    // 根据类型添加特定配置
    const type = channelData.type;
    switch (type) {
        case 'igot':
            channelData.IGOT_PUSH_KEY = document.getElementById('igot-key').value;
            break;
        case 'dingding':
            channelData.DD_BOT_TOKEN = document.getElementById('dd-bot-token').value;
            channelData.DD_BOT_SECRET = document.getElementById('dd-bot-secret').value;
            break;
        case 'feishu':
            channelData.FSKEY = document.getElementById('feishu-key').value;
            break;
        case 'chat':
            channelData.CHAT_URL = document.getElementById('chat-url').value;
            channelData.CHAT_TOKEN = document.getElementById('chat-token').value;
            break;
        case 'serverj':
            channelData.PUSH_KEY = document.getElementById('serverj-push-key').value;
            break;
        case 'wecom_app': {
            // 组装企业微信App所需的 QYWX_AM: corpid,corpsecret,touser,agentid[,media_id]
            const corpid = document.getElementById('weapp-corpid') ? document.getElementById('weapp-corpid').value.trim() : '';
            const corpsecret = document.getElementById('weapp-corpsecret') ? document.getElementById('weapp-corpsecret').value.trim() : '';
            const touser = document.getElementById('weapp-touser') ? document.getElementById('weapp-touser').value.trim() : '';
            const agentid = document.getElementById('weapp-agentid') ? document.getElementById('weapp-agentid').value.trim() : '';
            const media = document.getElementById('weapp-mediaid') ? document.getElementById('weapp-mediaid').value.trim() : '';
            const parts = [corpid, corpsecret, touser, agentid].filter(Boolean);
            if (media) parts.push(media);
            channelData.QYWX_AM = parts.join(',');
            break;
        }
        case 'wecom_bot':
            channelData.QYWX_KEY = document.getElementById('wecom-key').value;
            break;
        case 'telegram':
            channelData.TG_BOT_TOKEN = document.getElementById('tg-bot-token').value;
            channelData.TG_USER_ID = document.getElementById('tg-user-id').value;
            channelData.TG_API_HOST = document.getElementById('tg-api-host') ? document.getElementById('tg-api-host').value : '';
            channelData.TG_PROXY_HOST = document.getElementById('tg-proxy-host') ? document.getElementById('tg-proxy-host').value : '';
            channelData.TG_PROXY_PORT = document.getElementById('tg-proxy-port') ? document.getElementById('tg-proxy-port').value : '';
            channelData.TG_PROXY_AUTH = document.getElementById('tg-proxy-auth') ? document.getElementById('tg-proxy-auth').value : '';
            break;
        case 'smtp':
            channelData.SMTP_SERVER = document.getElementById('smtp-server').value;
            channelData.SMTP_EMAIL = document.getElementById('smtp-email').value;
            channelData.SMTP_PASSWORD = document.getElementById('smtp-password').value;
            channelData.SMTP_NAME = document.getElementById('smtp-name') ? document.getElementById('smtp-name').value : '';
            channelData.SMTP_SSL = document.getElementById('smtp-ssl') && document.getElementById('smtp-ssl').checked ? 'true' : 'false';
            // 如填写端口且 server 未包含端口，组合为 host:port（不覆盖用户显式写好的 host:port）
            (function combinePort() {
                const port = document.getElementById('smtp-port') ? document.getElementById('smtp-port').value.trim() : '';
                if (!port) return;
                const server = channelData.SMTP_SERVER || '';
                if (server && !server.includes(':')) {
                    channelData.SMTP_SERVER = server + ':' + port;
                }
            })();
            break;
        case 'bark':
            channelData.BARK_PUSH = document.getElementById('bark-url').value;
            channelData.BARK_GROUP = document.getElementById('bark-group') ? document.getElementById('bark-group').value : '';
            channelData.BARK_SOUND = document.getElementById('bark-sound') ? document.getElementById('bark-sound').value : '';
            channelData.BARK_ICON = document.getElementById('bark-icon') ? document.getElementById('bark-icon').value : '';
            channelData.BARK_LEVEL = document.getElementById('bark-level') ? document.getElementById('bark-level').value : '';
            channelData.BARK_URL = document.getElementById('bark-jump-url') ? document.getElementById('bark-jump-url').value : '';
            channelData.BARK_ARCHIVE = document.getElementById('bark-archive') && document.getElementById('bark-archive').checked ? '1' : '';
            break;
        case 'webhook':
            channelData.WEBHOOK_URL = document.getElementById('webhook-url').value;
            channelData.WEBHOOK_METHOD = document.getElementById('webhook-method').value;
            channelData.WEBHOOK_CONTENT_TYPE = document.getElementById('webhook-content-type').value;
            channelData.WEBHOOK_HEADERS = document.getElementById('webhook-headers').value;
            channelData.WEBHOOK_BODY = document.getElementById('webhook-body').value;
            break;
    }
    // 每渠道一言开关（默认 false）
    const perHitokoto = document.getElementById('channel-hitokoto');
    if (perHitokoto) {
        channelData.HITOKOTO = !!perHitokoto.checked;
    }
    
    try {
        // 先读取现有配置并合并，避免覆盖其它渠道
        const current = await fetch('/api/notify/config').then(r => r.json());
        const notifyCfg = (current && current.success && current.notify) ? current.notify : {};
        const enabledGlobal = document.getElementById('notifyEnabled').checked;
        const channels = { ...(notifyCfg.channels || {}) };
        const editingKey = form.dataset.editingKey || null;
        if (editingKey && editingKey !== channelData.name && channels[editingKey]) {
            // 支持重命名：删除旧key
            delete channels[editingKey];
        }
        channels[channelData.name] = channelData;
        const merged = {
            ...notifyCfg,
            enable: enabledGlobal,
            channels: channels
        };
        const response = await fetch('/api/notify/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ notify: merged })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('通知渠道已保存', 'success');
            bootstrap.Modal.getInstance(document.getElementById('notifyChannelModal')).hide();
            form.reset();
            // 清理编辑状态
            delete form.dataset.editingKey;
            loadNotifyConfig();
        } else {
            throw new Error(data.message || '保存失败');
        }
    } catch (error) {
        console.error('保存通知渠道失败:', error);
        showToast('保存失败: ' + error.message, 'danger');
    }
}

// 切换渠道启用状态
async function toggleChannel(channelKey, enabled) {
    try {
        // 获取并更新指定渠道的启用状态
        const current = await fetch('/api/notify/config').then(r => r.json());
        const notifyCfg = (current && current.success && current.notify) ? current.notify : {};
        const channels = { ...(notifyCfg.channels || {}) };
        if (!channels[channelKey]) {
            throw new Error('未找到该通知渠道');
        }
        channels[channelKey] = { ...channels[channelKey], enable: enabled };
        const merged = { ...notifyCfg, channels };
        const res = await fetch('/api/notify/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notify: merged })
        }).then(r => r.json());
        if (!res || res.success !== true) {
            throw new Error((res && res.message) || '保存失败');
        }
        showToast(`渠道已${enabled ? '启用' : '禁用'}`, 'success');
    } catch (error) {
        console.error('切换渠道状态失败:', error);
        showToast('操作失败: ' + error.message, 'danger');
    }
}

// 编辑渠道
async function editChannel(channelKey) {
    try {
        const current = await fetch('/api/notify/config').then(r => r.json());
        const notifyCfg = (current && current.success && current.notify) ? current.notify : {};
        const channels = notifyCfg.channels || {};
        const ch = channels[channelKey];
        if (!ch) {
            showToast('未找到该通知渠道', 'danger');
            return;
        }
        const form = document.getElementById('notify-channel-form');
        if (!form) return;
        // 标记编辑key
        form.dataset.editingKey = channelKey;
        // 基础字段
        const nameInput = document.getElementById('channel-name');
        const typeSelect = document.getElementById('channel-type');
        const enableSwitch = document.getElementById('channel-enable');
        if (nameInput) nameInput.value = ch.name || channelKey;
        if (typeSelect) typeSelect.value = ch.type || 'webhook';
        if (enableSwitch) enableSwitch.checked = !!ch.enable;

        // 显示对应配置区域
        showChannelConfig();

        // 根据类型填充专有字段
        const type = (ch.type || 'webhook');
        switch (type) {
        case 'wecom_app': {
            // 将UI字段拼装为后端期望的 QYWX_AM 格式（corpid,corpsecret,touser,agentid[,media_id])
            const corpid = document.getElementById('weapp-corpid') ? document.getElementById('weapp-corpid').value.trim() : '';
            const corpsecret = document.getElementById('weapp-corpsecret') ? document.getElementById('weapp-corpsecret').value.trim() : '';
            const touser = document.getElementById('weapp-touser') ? document.getElementById('weapp-touser').value.trim() : '';
            const agentid = document.getElementById('weapp-agentid') ? document.getElementById('weapp-agentid').value.trim() : '';
            const media = document.getElementById('weapp-mediaid') ? document.getElementById('weapp-mediaid').value.trim() : '';
            const parts = [corpid, corpsecret, touser, agentid].filter(Boolean);
            if (media) parts.push(media);
            channelData.QYWX_AM = parts.join(',');
            break;
        }
            case 'wecom_app': {
                const q = ch.QYWX_AM || '';
                const arr = q.split(',');
                const c1 = document.getElementById('weapp-corpid');
                const c2 = document.getElementById('weapp-corpsecret');
                const c3 = document.getElementById('weapp-touser');
                const c4 = document.getElementById('weapp-agentid');
                const c5 = document.getElementById('weapp-mediaid');
                if (c1) c1.value = arr[0] || '';
                if (c2) c2.value = arr[1] || '';
                if (c3) c3.value = arr[2] || '';
                if (c4) c4.value = arr[3] || '';
                if (c5) c5.value = arr[4] || '';
                break;
            }
            case 'igot': {
                const k = document.getElementById('igot-key');
                if (k) k.value = ch.IGOT_PUSH_KEY || '';
                break;
            }
            case 'dingding': {
                const t = document.getElementById('dd-bot-token');
                const s = document.getElementById('dd-bot-secret');
                if (t) t.value = ch.DD_BOT_TOKEN || '';
                if (s) s.value = ch.DD_BOT_SECRET || '';
                break;
            }
            case 'feishu': {
                const f = document.getElementById('feishu-key');
                if (f) f.value = ch.FSKEY || '';
                break;
            }
            case 'chat': {
                const u = document.getElementById('chat-url');
                const t = document.getElementById('chat-token');
                if (u) u.value = ch.CHAT_URL || '';
                if (t) t.value = ch.CHAT_TOKEN || '';
                break;
            }
            case 'serverj': {
                const s = document.getElementById('serverj-push-key');
                if (s) s.value = ch.PUSH_KEY || '';
                break;
            }
            case 'wecom_bot': {
                const el = document.getElementById('wecom-key');
                if (el) el.value = ch.QYWX_KEY || '';
                break;
            }
            case 'telegram': {
                const t1 = document.getElementById('tg-bot-token');
                const t2 = document.getElementById('tg-user-id');
                const t3 = document.getElementById('tg-api-host');
                const t4 = document.getElementById('tg-proxy-host');
                const t5 = document.getElementById('tg-proxy-port');
                const t6 = document.getElementById('tg-proxy-auth');
                if (t1) t1.value = ch.TG_BOT_TOKEN || '';
                if (t2) t2.value = ch.TG_USER_ID || '';
                if (t3) t3.value = ch.TG_API_HOST || '';
                if (t4) t4.value = ch.TG_PROXY_HOST || '';
                if (t5) t5.value = ch.TG_PROXY_PORT || '';
                if (t6) t6.value = ch.TG_PROXY_AUTH || '';
                break;
            }
            case 'smtp': {
                const s1 = document.getElementById('smtp-server');
                const s2 = document.getElementById('smtp-port');
                const s3 = document.getElementById('smtp-email');
                const s4 = document.getElementById('smtp-password');
                const s5 = document.getElementById('smtp-name');
                const s6 = document.getElementById('smtp-ssl');
                const serverVal = ch.SMTP_SERVER || '';
                if (s1) s1.value = serverVal;
                if (s2) {
                    const idx = serverVal.lastIndexOf(':');
                    s2.value = idx > -1 ? serverVal.slice(idx + 1) : '';
                }
                if (s3) s3.value = ch.SMTP_EMAIL || '';
                if (s4) s4.value = ch.SMTP_PASSWORD || '';
                if (s5) s5.value = ch.SMTP_NAME || '';
                if (s6) s6.checked = String(ch.SMTP_SSL || 'false') === 'true';
                break;
            }
            case 'bark': {
                const b0 = document.getElementById('bark-url');
                const b1 = document.getElementById('bark-group');
                const b2 = document.getElementById('bark-sound');
                const b3 = document.getElementById('bark-icon');
                const b4 = document.getElementById('bark-level');
                const b5 = document.getElementById('bark-jump-url');
                const b6 = document.getElementById('bark-archive');
                if (b0) b0.value = ch.BARK_PUSH || '';
                if (b1) b1.value = ch.BARK_GROUP || '';
                if (b2) b2.value = ch.BARK_SOUND || '';
                if (b3) b3.value = ch.BARK_ICON || '';
                if (b4) b4.value = ch.BARK_LEVEL || '';
                if (b5) b5.value = ch.BARK_URL || '';
                if (b6) b6.checked = !!(ch.BARK_ARCHIVE && String(ch.BARK_ARCHIVE) !== '0' && String(ch.BARK_ARCHIVE).toLowerCase() !== 'false');
                break;
            }
            
            case 'webhook':
            default: {
                const u = document.getElementById('webhook-url');
                const m = document.getElementById('webhook-method');
                const ct = document.getElementById('webhook-content-type');
                const hd = document.getElementById('webhook-headers');
                const bd = document.getElementById('webhook-body');
                if (u) u.value = ch.WEBHOOK_URL || '';
                if (m) m.value = ch.WEBHOOK_METHOD || 'POST';
                if (ct) ct.value = ch.WEBHOOK_CONTENT_TYPE || 'application/json';
                if (hd) hd.value = ch.WEBHOOK_HEADERS || '';
                if (bd) bd.value = ch.WEBHOOK_BODY || '';
                break;
            }
        }
        // 预填每渠道一言
        const hitokotoEl = document.getElementById('channel-hitokoto');
        if (hitokotoEl) hitokotoEl.checked = !!ch.HITOKOTO;

        // 设置模态框标题/按钮
        const titleEl = document.getElementById('notifyChannelModalLabel');
        const saveBtn = document.getElementById('save-notify-channel');
        if (titleEl) titleEl.textContent = '编辑通知渠道';
        if (saveBtn) saveBtn.textContent = '更新';

        // 打开模态框
        const modal = new bootstrap.Modal(document.getElementById('notifyChannelModal'));
        modal.show();
    } catch (e) {
        console.error('加载渠道配置失败:', e);
        showToast('加载渠道配置失败: ' + e.message, 'danger');
    }
}

// 新增渠道：打开模态框并重置表单
function openAddNotifyChannelModal() {
    const form = document.getElementById('notify-channel-form');
    if (form) {
        form.reset();
        delete form.dataset.editingKey;
    }
    const titleEl = document.getElementById('notifyChannelModalLabel');
    const saveBtn = document.getElementById('save-notify-channel');
    if (titleEl) titleEl.textContent = '添加通知渠道';
    if (saveBtn) saveBtn.textContent = '保存';
    const typeSelect = document.getElementById('channel-type');
    if (typeSelect) {
        // 重置并隐藏所有专有配置
        typeSelect.value = '';
        document.querySelectorAll('.channel-config').forEach(el => el.style.display = 'none');
    }
}

// 删除渠道
async function deleteChannel(channelKey) {
    showConfirmModal('确认删除', '确定要删除这个通知渠道吗？', function onConfirm() {
        performDeleteChannel(channelKey);
    });
}

// 执行删除渠道操作
async function performDeleteChannel(channelKey) {
    try {
        // 获取现有配置并删除指定渠道
        const current = await fetch('/api/notify/config').then(r => r.json());
        const notifyCfg = (current && current.success && current.notify) ? current.notify : {};
        const channels = { ...(notifyCfg.channels || {}) };
        if (!channels[channelKey]) {
            throw new Error('未找到该通知渠道');
        }
        delete channels[channelKey];
        const merged = { ...notifyCfg, channels };
        const res = await fetch('/api/notify/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notify: merged })
        }).then(r => r.json());
        if (!res || res.success !== true) {
            throw new Error((res && res.message) || '删除失败');
        }
        showToast('渠道已删除', 'success');
        loadNotifyConfig();
    } catch (error) {
        console.error('删除渠道失败:', error);
        showToast('删除失败: ' + error.message, 'danger');
    }
}

// 单渠道测试
async function testSingleChannel(channelKey) {
    try {
        const current = await fetch('/api/notify/config').then(r => r.json());
        const notifyCfg = (current && current.success && current.notify) ? current.notify : {};
        const channels = notifyCfg.channels || {};
        const ch = channels[channelKey];
        if (!ch) {
            showToast('渠道不存在', 'warning');
            return;
        }
        if (!ch.enable) {
            showToast('该渠道未启用', 'warning');
            return;
        }
        const payload = { title: 'PT-Accelerator通知测试', content: '这是一条测试消息，用于验证通知功能是否正常工作。', channels: {} };
        payload.channels[channelKey] = ch;

        const resp = await fetch('/api/notify/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (data.success) {
            showToast('测试通知已发送', 'success');
        } else {
            throw new Error(data.message || '发送失败');
        }
    } catch (error) {
        console.error('测试通知失败:', error);
        showToast('测试失败: ' + error.message, 'danger');
    }
}

// ===== 通知设置功能 END =====