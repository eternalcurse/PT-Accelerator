/**
 * 下载器管理相关功能 - 支持多实例动态管理
 */

// 全局变量
let currentClients = [];
let supportedClientTypes = [];

// 初始化下载器配置界面
function initTorrentClientsUI() {
    console.log('初始化下载器客户端管理界面');
    
    // 加载支持的客户端类型
    loadSupportedClientTypes();
    
    // 加载现有客户端配置
    loadTorrentClients();
    
    // 绑定按钮事件
    bindTorrentClientEvents();
}

// 加载支持的客户端类型
function loadSupportedClientTypes() {
    $.ajax({
        url: "/api/torrent-client-types",
        type: "GET",
        timeout: 10000,
        success: function(response) {
            if (response.success) {
                supportedClientTypes = response.types;
                console.log('加载客户端类型成功:', supportedClientTypes);
            }
        },
        error: function(xhr, status, error) {
            console.error('加载客户端类型失败:', error);
            showToast("加载客户端类型失败: " + error, "danger", 10000);
        }
    });
}

// 加载下载器客户端配置
function loadTorrentClients() {
    console.log('加载下载器客户端配置');
    $.ajax({
        url: "/api/torrent-clients",
        type: "GET",
        timeout: 10000,
        success: function(response) {
            if (response.success) {
                currentClients = response.clients || [];
                renderTorrentClients();
                console.log('加载客户端配置成功:', currentClients);
            } else {
                showToast("加载客户端配置失败: " + response.message, "danger", 10000);
            }
        },
        error: function(xhr, status, error) {
            console.error('加载客户端配置失败:', status, error);
            if (status === "timeout") {
                showToast("加载客户端配置超时，请检查网络连接", "warning", 10000);
            } else {
                showToast("加载客户端配置失败: " + error, "danger", 10000);
            }
        }
    });
}

// 渲染客户端列表
function renderTorrentClients() {
    const container = $("#torrent-clients-container");
    container.empty();
    
    // 添加客户端按钮
    const addButtonHtml = `
        <div class="d-flex flex-column flex-md-row justify-content-between align-items-start align-items-md-center mb-3">
            <h5 class="mb-3 mb-md-0"><i class="bi bi-download me-2"></i>下载器管理</h5>
            <div class="d-flex flex-wrap align-items-center gap-2">
                <button class="btn btn-success d-flex align-items-center text-nowrap" id="btn-import-trackers">
                    <i class="bi bi-cloud-download me-1"></i> 导入Tracker
                </button>
                <button class="btn btn-primary d-flex align-items-center text-nowrap" id="btn-add-client">
                    <i class="bi bi-plus-circle me-1"></i> 添加下载器
                </button>
            </div>
        </div>
    `;
    container.append(addButtonHtml);
    
    // 渲染每个客户端
    currentClients.forEach((client, index) => {
        const clientHtml = createClientCard(client, index);
        container.append(clientHtml);
    });
    
    // 如果没有客户端，显示提示
    if (currentClients.length === 0) {
        const emptyHtml = `
            <div class="card">
                <div class="card-body text-center">
                    <i class="bi bi-info-circle fs-1 text-muted"></i>
                    <h5 class="mt-3">暂无下载器配置</h5>
                    <p class="text-muted">点击"添加下载器"按钮开始配置您的下载器客户端</p>
                </div>
            </div>
        `;
        container.append(emptyHtml);
    }
}

// 创建客户端卡片
function createClientCard(client, index) {
    const clientType = supportedClientTypes.find(type => type.type === client.type) || {};
    const typeName = clientType.name || client.type;
    
    return `
        <div class="card mb-3" data-client-id="${client.id}">
            <div class="card-header d-flex flex-column flex-sm-row align-items-start align-items-sm-center justify-content-between">
                <div class="mb-2 mb-sm-0">
                    <span class="fw-bold">${client.name}</span>
                    <span class="badge bg-secondary ms-2">${typeName}</span>
                    ${client.enable ? '<span class="badge bg-success ms-1">已启用</span>' : '<span class="badge bg-secondary ms-1">已禁用</span>'}
                </div>
                <div class="d-flex flex-row flex-wrap align-items-center gap-1">
                    <button class="btn btn-sm btn-outline-info d-flex align-items-center text-nowrap" onclick="testClientConnection('${client.id}')">
                        <i class="bi bi-check-circle me-1"></i> 测试
                    </button>
                    <button class="btn btn-sm btn-outline-primary d-flex align-items-center text-nowrap" onclick="editClient('${client.id}')">
                        <i class="bi bi-pencil me-1"></i> 编辑
                    </button>
                    <button class="btn btn-sm btn-outline-danger d-flex align-items-center text-nowrap" onclick="deleteClient('${client.id}')">
                        <i class="bi bi-trash me-1"></i> 删除
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <small class="text-muted">连接地址:</small><br>
                        <span>${client.use_https ? 'https' : 'http'}://${client.host}:${client.port}</span>
                    </div>
                    <div class="col-md-6">
                        <small class="text-muted">用户名:</small><br>
                        <span>${client.username || '(未设置)'}</span>
                    </div>
                    ${client.type === 'transmission' ? `
                    <div class="col-md-6 mt-2">
                        <small class="text-muted">RPC路径:</small><br>
                        <span>${client.path || '/transmission/rpc'}</span>
                    </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
}

// 绑定事件
function bindTorrentClientEvents() {
    // 先解绑所有相关事件，避免重复绑定
    $(document).off('click', '#btn-add-client');
    $(document).off('click', '#btn-import-trackers');
    $(document).off('click', '#save-clients-btn');
    
    // 添加客户端
    $(document).on('click', '#btn-add-client', function() {
        showClientModal();
    });
    
    // 导入Tracker
    $(document).on('click', '#btn-import-trackers', function() {
        importTrackersFromClients();
    });
    
    // 保存所有配置
    $(document).on('click', '#save-clients-btn', function() {
        saveTorrentClients();
    });
}

// 显示客户端配置模态框
function showClientModal(clientId = null) {
    const isEdit = clientId !== null;
    const client = isEdit ? currentClients.find(c => c.id === clientId) : null;
    
    let modalHtml = `
        <div class="modal fade" id="clientModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${isEdit ? '编辑' : '添加'}下载器</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="clientForm">
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="form-floating mb-3">
                                        <input type="text" class="form-control" id="client-name" placeholder="客户端名称" required
                                               value="${client ? client.name : ''}">
                                        <label for="client-name">客户端名称 *</label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-floating mb-3">
                                        <select class="form-control" id="client-type" required ${isEdit ? 'disabled' : ''}>
                                            <option value="">选择类型</option>
                                            ${supportedClientTypes.map(type => 
                                                `<option value="${type.type}" ${client && client.type === type.type ? 'selected' : ''}>${type.name}</option>`
                                            ).join('')}
                                        </select>
                                        <label for="client-type">客户端类型 *</label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-floating mb-3">
                                        <input type="text" class="form-control" id="client-host" placeholder="主机地址" required
                                               value="${client ? client.host : 'localhost'}">
                                        <label for="client-host">主机地址 *</label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-floating mb-3">
                                        <input type="number" class="form-control" id="client-port" placeholder="端口" min="1" max="65535" required
                                               value="${client ? client.port : ''}">
                                        <label for="client-port">端口 *</label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-floating mb-3">
                                        <input type="text" class="form-control" id="client-username" placeholder="用户名"
                                               value="${client ? client.username : ''}">
                                        <label for="client-username">用户名</label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-floating mb-3">
                                        <input type="password" class="form-control" id="client-password" placeholder="密码"
                                               value="${client ? client.password : ''}">
                                        <label for="client-password">密码</label>
                                    </div>
                                </div>
                                <div class="col-md-6" id="transmission-path-group" style="display: none;">
                                    <div class="form-floating mb-3">
                                        <input type="text" class="form-control" id="client-path" placeholder="RPC路径"
                                               value="${client ? client.path : '/transmission/rpc'}">
                                        <label for="client-path">RPC路径</label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-check form-switch mt-3">
                                        <input class="form-check-input" type="checkbox" id="client-https"
                                               ${client && client.use_https ? 'checked' : ''}>
                                        <label class="form-check-label" for="client-https">使用HTTPS</label>
                                    </div>
                                    <div class="form-check form-switch mt-2">
                                        <input class="form-check-input" type="checkbox" id="client-enable"
                                               ${!client || client.enable ? 'checked' : ''}>
                                        <label class="form-check-label" for="client-enable">启用客户端</label>
                                    </div>
                                </div>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-outline-info" id="test-client-btn">
                            <i class="bi bi-check-circle"></i>测试连接
                        </button>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" id="save-client-btn">
                            <i class="bi bi-check"></i>${isEdit ? '保存' : '添加'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // 移除现有模态框
    $('#clientModal').remove();
    
    // 添加模态框到页面
    $('body').append(modalHtml);
    
    // 绑定事件
    bindClientModalEvents(isEdit, clientId);
    
    // 显示模态框
    $('#clientModal').modal('show');
    
    // 根据类型显示/隐藏特定字段
    updateClientFormFields();
}

// 绑定客户端模态框事件
function bindClientModalEvents(isEdit, clientId) {
    // 类型变化时更新表单字段
    $('#client-type').on('change', updateClientFormFields);
    
    // 测试连接
    $('#test-client-btn').on('click', function() {
        testClientConnectionInModal();
    });
    
    // 保存客户端
    $('#save-client-btn').on('click', function() {
        saveClientFromModal(isEdit, clientId);
    });
}

// 更新客户端表单字段
function updateClientFormFields() {
    const selectedType = $('#client-type').val();
    const clientType = supportedClientTypes.find(type => type.type === selectedType);
    
    if (clientType) {
        // 设置默认端口
        if (!$('#client-port').val()) {
            $('#client-port').val(clientType.default_port);
        }
        
        // 显示/隐藏Transmission特有字段
        if (selectedType === 'transmission') {
            $('#transmission-path-group').show();
        } else {
            $('#transmission-path-group').hide();
        }
    }
}

// 在模态框中测试连接
function testClientConnectionInModal() {
    const clientConfig = getClientConfigFromModal();
    
    if (!validateClientConfig(clientConfig)) {
        return;
    }
    
    $.ajax({
        url: "/api/test-client-connection",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({
            client_config: clientConfig
        }),
        timeout: 15000,
        beforeSend: function() {
            $('#test-client-btn').prop('disabled', true).html('<i class="spinner-border spinner-border-sm me-1"></i>测试中...');
        },
        success: function(response) {
            if (response.success) {
                showToast(response.message, "success", 8000);
            } else {
                showToast(response.message || "连接测试失败", "danger", 10000);
            }
        },
        error: function(xhr, status, error) {
            console.error('测试连接失败:', status, error);
            if (status === "timeout") {
                showToast("连接测试超时，请检查地址和端口是否正确", "warning", 10000);
            } else {
                showToast("测试连接失败: " + error, "danger", 10000);
            }
        },
        complete: function() {
            $('#test-client-btn').prop('disabled', false).html('<i class="bi bi-check-circle"></i>测试连接');
        }
    });
}

// 从模态框获取客户端配置
function getClientConfigFromModal() {
    return {
        name: $('#client-name').val().trim(),
        type: $('#client-type').val(),
        host: $('#client-host').val().trim(),
        port: parseInt($('#client-port').val()) || 0,
        username: $('#client-username').val().trim(),
        password: $('#client-password').val(),
        use_https: $('#client-https').prop('checked'),
        path: $('#client-path').val().trim() || '/transmission/rpc',
        enable: $('#client-enable').prop('checked')
    };
}

// 验证客户端配置
function validateClientConfig(config) {
    if (!config.name) {
        showToast("请输入客户端名称", "warning", 5000);
        return false;
    }
    
    if (!config.type) {
        showToast("请选择客户端类型", "warning", 5000);
        return false;
    }
    
    if (!config.host) {
        showToast("请输入主机地址", "warning", 5000);
        return false;
    }
    
    if (!config.port || config.port < 1 || config.port > 65535) {
        showToast("请输入有效的端口号(1-65535)", "warning", 5000);
        return false;
    }
    
    return true;
}

// 从模态框保存客户端
function saveClientFromModal(isEdit, clientId) {
    const clientConfig = getClientConfigFromModal();
    
    if (!validateClientConfig(clientConfig)) {
        return;
    }
    
    if (isEdit) {
        // 编辑现有客户端
        const index = currentClients.findIndex(c => c.id === clientId);
        if (index !== -1) {
            currentClients[index] = { ...currentClients[index], ...clientConfig };
        }
    } else {
        // 添加新客户端
        const newId = generateClientId(clientConfig.type);
        clientConfig.id = newId;
        currentClients.push(clientConfig);
    }
    
    // 保存所有客户端配置
    saveTorrentClients();
    
    // 关闭模态框
    $('#clientModal').modal('hide');
}

// 生成客户端ID
function generateClientId(type) {
    const timestamp = Date.now();
    const random = Math.floor(Math.random() * 1000);
    return `${type}_${timestamp}_${random}`;
}

// 保存所有下载器客户端配置
function saveTorrentClients() {
    console.log('保存下载器客户端配置:', currentClients);
    
    $.ajax({
        url: "/api/torrent-clients",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({
            clients: currentClients
        }),
        timeout: 15000,
        beforeSend: function() {
            showToast("正在保存配置...", "info", 3000);
        },
        success: function(response) {
            if (response.success) {
                showToast(response.message, "success", 5000);
                // 重新从后端加载最新配置，确保前后端状态同步
                loadTorrentClients();
            } else {
                showToast(response.message || "保存配置失败", "danger", 10000);
            }
        },
        error: function(xhr, status, error) {
            console.error('保存配置失败:', status, error);
            if (status === "timeout") {
                showToast("保存配置超时，请重试", "warning", 10000);
            } else {
                showToast("保存配置失败: " + error, "danger", 10000);
            }
        }
    });
}

// 测试客户端连接
function testClientConnection(clientId) {
    const client = currentClients.find(c => c.id === clientId);
    if (!client) {
        showToast("未找到客户端配置", "danger", 5000);
        console.error('未找到客户端配置:', clientId, '当前客户端列表:', currentClients);
        return;
    }
    
    console.log('测试客户端连接:', clientId, '客户端配置:', client);
    
    $.ajax({
        url: "/api/test-client-connection",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({
            client_id: clientId
        }),
        timeout: 15000,
        beforeSend: function() {
            $(`[data-client-id="${clientId}"] .btn-outline-info`).prop('disabled', true)
                .html('<i class="spinner-border spinner-border-sm"></i>');
        },
        success: function(response) {
            if (response.success) {
                showToast(response.message, "success", 8000);
            } else {
                showToast(response.message || "连接测试失败", "danger", 10000);
            }
        },
        error: function(xhr, status, error) {
            console.error('测试连接失败:', status, error);
            if (status === "timeout") {
                showToast("连接测试超时，请检查配置", "warning", 10000);
            } else {
                showToast("测试连接失败: " + error, "danger", 10000);
            }
        },
        complete: function() {
            $(`[data-client-id="${clientId}"] .btn-outline-info`).prop('disabled', false)
                .html('<i class="bi bi-check-circle"></i>测试');
        }
    });
}

// 编辑客户端
function editClient(clientId) {
    showClientModal(clientId);
}

// 删除客户端
function deleteClient(clientId) {
    const client = currentClients.find(c => c.id === clientId);
    if (!client) {
        showToast("未找到客户端配置", "danger", 5000);
        return;
    }
    
    showConfirmModal('确认删除', `确定要删除客户端 "${client.name}" 吗？`, function onConfirm() {
        performDeleteClient(clientId);
    });
}

// 执行删除客户端操作
function performDeleteClient(clientId) {
    $.ajax({
        url: `/api/torrent-clients/${clientId}`,
        type: "DELETE",
        timeout: 10000,
        success: function(response) {
            if (response.success) {
                showToast(response.message, "success", 5000);
                // 从本地数组中移除
                currentClients = currentClients.filter(c => c.id !== clientId);
                renderTorrentClients();
            } else {
                showToast(response.message || "删除失败", "danger", 10000);
            }
        },
        error: function(xhr, status, error) {
            console.error('删除客户端失败:', status, error);
            showToast("删除客户端失败: " + error, "danger", 10000);
        }
    });
}

// 从下载器导入Tracker
function importTrackersFromClients() {
    // 检查是否有启用的客户端
    const enabledClients = currentClients.filter(c => c.enable);
    if (enabledClients.length === 0) {
        showToast("请先启用至少一个下载器客户端", "warning", 8000);
        return;
    }
    
    $.ajax({
        url: "/api/import-trackers-from-clients",
        type: "POST",
        timeout: 30000,
        beforeSend: function() {
            $('#btn-import-trackers').prop('disabled', true)
                .html('<i class="spinner-border spinner-border-sm me-1"></i>导入中...');
        },
        success: function(response) {
            const messageType = response.status === "success" ? "success" : 
                               response.status === "warning" ? "warning" : "danger";
            
            let message = response.message;
            if (response.client_summary) {
                message += `<br><small>详情：${response.client_summary}</small>`;
            }
            
            showToast(message, messageType, 10000);
            
            // 如果成功导入，刷新tracker列表和hosts文件显示
            if (response.status === "success" && typeof loadTrackers === 'function') {
                setTimeout(loadTrackers, 1000);
                // 同时更新hosts文件显示
                if (typeof loadCurrentHosts === 'function') {
                    setTimeout(loadCurrentHosts, 2000);
                }
            }
        },
        error: function(xhr, status, error) {
            console.error('导入Tracker失败:', status, error);
            if (status === "timeout") {
                showToast("导入Tracker超过30秒，可能tracker数量较多，程序仍在后台导入，请耐心等待并稍后查看tracker列表", "warning", 15000);
            } else {
                showToast("导入Tracker失败: " + error, "danger", 10000);
            }
        },
        complete: function() {
            $('#btn-import-trackers').prop('disabled', false)
                .html('<i class="bi bi-cloud-download"></i>导入Tracker');
        }
    });
}

// 新增 DOMContentLoaded 事件监听器确保只初始化一次
document.addEventListener('DOMContentLoaded', function() {
    console.log('Torrent clients UI DOM fully loaded, initializing.');
    initTorrentClientsUI();
});