// worker/index.js
// Cloudflare Workers - Multi-Task GitHub Actions Trigger

// 任务映射表：将 Cron 表达式与 {id: 文件名, input: Actions参数} 关联起来
// Cron 表达式已精确转换为 UTC 时间
const CRON_TO_WORKFLOW = {
    // =========================================================================
    // 1. cleaner.yml (每周清理)
    // 表达式: 0 19 * * 7 (每周日 UTC 19:00)
    "0 19 * * 7": { 
        id: "cleaner.yml", 
        description: "Weekly Cleanup (cleaner.yml)",
        input: {} // 清理任务无需额外参数
    },
    // =========================================================================
    // 2. scheduler.yml - TASK_1 (每日 06:00 CST 启动)
    // 表达式: 0 22 * * * (每日 UTC 22:00)
    "0 22 * * *": { 
        id: "scheduler.yml", 
        description: "Daily Schedule (TASK_1)",
        input: { task_to_run: "TASK_1" } // 传入任务ID
    },
    // =========================================================================
    // 3. scheduler.yml - TASK_2 (每 4 小时一次，比 T1 晚 10 分钟)
    // 表达式: 10 2,6,10,14,18,22 * * * (UTC 02:10, 06:10, 10:10, 14:10, 18:10, 22:10)
    "10 2,6,10,14,18,22 * * *": { 
        id: "scheduler.yml", 
        description: "4-Hourly Schedule (TASK_2)",
        input: { task_to_run: "TASK_2" } // 传入任务ID
    },
    // =========================================================================
    // 4. scheduler.yml - TASK_3 (每 30 分钟一次，比 T1 晚 15 分钟)
    // 表达式: 15,45 0-15,22-23 * * * (UTC 0-15 & 22-23 小时，每小时 15/45 分)
    "15,45 0-15,22-23 * * *": { 
        id: "scheduler.yml", 
        description: "Half-Hourly Schedule (TASK_3)",
        input: { task_to_run: "TASK_3" } // 传入任务ID
    }
};


export default {
    async scheduled(event, env, ctx) {
        const { WORKER_GITHUB_PAT, GITHUB_OWNER, GITHUB_REPO, TARGET_BRANCH } = env;
        
        // 1. 根据触发的 Cron 表达式 (event.cron) 查找对应的工作流配置
        const taskConfig = CRON_TO_WORKFLOW[event.cron];

        if (!taskConfig) {
            console.error(`ERROR: No workflow configured for Cron expression: ${event.cron}`);
            return;
        }
        
        const WORKFLOW_ID = taskConfig.id;
        const taskDescription = taskConfig.description;

        if (!WORKER_GITHUB_PAT) {
            console.error("FATAL ERROR: WORKER_GITHUB_PAT is missing or invalid in Worker environment.");
            throw new Error("Worker failed: Missing GitHub PAT Secret.");
        }

        // 2. 构造 API URL 和请求体
        const apiUrl = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_ID}/dispatches`;

        const requestBody = JSON.stringify({
            ref: TARGET_BRANCH || "main", 
            inputs: taskConfig.input // 动态传递任务参数
        });

        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': `token ${WORKER_GITHUB_PAT}`,
            'User-Agent': `Cloudflare-Worker-${taskDescription}`,
            'Content-Type': 'application/json',
        };

        // 3. 执行 POST 请求
        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: headers,
                body: requestBody,
            });

            if (response.status === 204) {
                console.log(`SUCCESS: ${taskDescription} triggered by cron: ${event.cron}`);
            } else {
                const errorText = await response.text();
                console.error(`FAILURE: Workflow trigger failed for ${WORKFLOW_ID} (Status: ${response.status}): ${errorText}`);
                throw new Error(`GitHub API Error for ${WORKFLOW_ID}: ${response.status}`);
            }
        } catch (error) {
            console.error('Fetch error:', error);
            throw error;
        }
    }
};