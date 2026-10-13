-- 智识有方 用户系统 / 学习数据 MySQL 8.x 表结构（utf8mb4）
-- 幂等：全部 IF NOT EXISTS，可重复执行（ensure_schema 调用）。
-- 归属模型：登录用户桶 "u:<username>"，匿名浏览器桶 "c:<id>"，二者在
-- wrongbook / mindmap / course_access 中以 owner_username / client_id 拆分存储。

-- ---------- 账号 ----------
CREATE TABLE IF NOT EXISTS users (
    id           INT          NOT NULL AUTO_INCREMENT,
    username     VARCHAR(32)  NOT NULL,
    salt         CHAR(32)     NOT NULL,
    password_hash CHAR(64)    NOT NULL,
    role         ENUM('admin','user') NOT NULL DEFAULT 'user',
    created_at   BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 浏览器 ↔ 账号 绑定 ----------
CREATE TABLE IF NOT EXISTS client_bindings (
    id          INT          NOT NULL AUTO_INCREMENT,
    client_id   VARCHAR(64)  NOT NULL,
    username    VARCHAR(32)  NOT NULL,
    bound_at    BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_cb_client (client_id),
    KEY idx_cb_user (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 按用户画像（JSON 列）----------
CREATE TABLE IF NOT EXISTS profiles (
    username    VARCHAR(32)  NOT NULL,
    profile_json LONGTEXT    NULL,
    updated_at  BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 课程访问归属（哪桶访问过哪门课；进度本身全局共享）----------
CREATE TABLE IF NOT EXISTS course_access (
    id           INT          NOT NULL AUTO_INCREMENT,
    owner        VARCHAR(64)  NOT NULL,
    course       VARCHAR(255) NOT NULL,
    last_access_at BIGINT    NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ca_owner_course (owner, course),
    KEY idx_ca_course (course)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 方案课程（全局，一门课一行；勾选进度在 plan_items）----------
CREATE TABLE IF NOT EXISTS plan_courses (
    id           INT          NOT NULL AUTO_INCREMENT,
    course       VARCHAR(255) NOT NULL,
    created_at   BIGINT       NOT NULL DEFAULT 0,
    last_seen_at BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_pc_course (course)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 方案大纲 / 计划勾选项 ----------
-- owner 归属桶（"u:<用户名>" 或 client_id），保证勾选/重点标注跟随个人账户隔离。
CREATE TABLE IF NOT EXISTS plan_items (
    id           INT          NOT NULL AUTO_INCREMENT,
    course_id    INT          NOT NULL,
    owner        VARCHAR(96)  NOT NULL DEFAULT '',
    kind         ENUM('outline','plan') NOT NULL,
    title        VARCHAR(512) NOT NULL DEFAULT '',
    done         TINYINT(1)   NOT NULL DEFAULT 0,
    importance   TINYINT(1)   NOT NULL DEFAULT 0,
    sort_order   INT          NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_pi_course (course_id),
    KEY idx_pi_owner (owner, course_id),
    CONSTRAINT fk_pi_course FOREIGN KEY (course_id)
        REFERENCES plan_courses (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 方案结果（按归属隔离：同一课程不同账号/浏览器各自存一份）----------
CREATE TABLE IF NOT EXISTS plan_results (
    course_id    INT          NOT NULL,
    owner        VARCHAR(96)  NOT NULL DEFAULT '',
    result_json  LONGTEXT     NULL,
    generated_at BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (course_id, owner),
    CONSTRAINT fk_pr_course FOREIGN KEY (course_id)
        REFERENCES plan_courses (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 错题本（按归属桶隔离）----------
CREATE TABLE IF NOT EXISTS wrongbook (
    id            INT          NOT NULL AUTO_INCREMENT,
    owner_username VARCHAR(32) NULL,
    client_id     VARCHAR(64)  NULL,
    course        VARCHAR(255) NOT NULL DEFAULT '未归类',
    question      LONGTEXT     NOT NULL,
    my_answer     LONGTEXT     NULL,
    answer        LONGTEXT     NULL,
    reason        VARCHAR(1000) NULL,
    tags          LONGTEXT     NULL,
    mastered      TINYINT(1)   NOT NULL DEFAULT 0,
    review_count  INT          NOT NULL DEFAULT 0,
    created_at    BIGINT       NOT NULL DEFAULT 0,
    updated_at    BIGINT       NOT NULL DEFAULT 0,
    last_review_at BIGINT     NULL,
    source        VARCHAR(64)  NULL,
    PRIMARY KEY (id),
    KEY idx_wb_owner (owner_username, course),
    KEY idx_wb_client (client_id, course),
    KEY idx_wb_mastered (mastered)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 思维导图（按归属桶隔离，一课程一图）----------
CREATE TABLE IF NOT EXISTS mindmap (
    id            INT          NOT NULL AUTO_INCREMENT,
    owner_username VARCHAR(32) NULL,
    client_id     VARCHAR(64)  NULL,
    course        VARCHAR(255) NOT NULL,
    nodes         LONGTEXT     NULL,
    updated_at    BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_mm_owner_course (owner_username, course),
    UNIQUE KEY uq_mm_client_course (client_id, course)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- 匿名 LLM 调用限速（防团队 token 被刷完）----------
-- 双闸：每浏览器每日 (bucket="anon:<client_id>") + 全局匿名每日池 (bucket="anon:global")。
-- count 在本日窗口内对全部 LLM 端点（chat/plan/quiz 出题）聚合计数。
-- 登录用户不受此限；MySQL 不可用（DbUnavailable）时 fail-open 放行。
CREATE TABLE IF NOT EXISTS rate_limits (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    bucket      VARCHAR(64)  NOT NULL,
    day         VARCHAR(10)  NOT NULL,
    count       INT          NOT NULL DEFAULT 0,
    updated_at  BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_rl_bucket_day (bucket, day),
    KEY idx_rl_day (day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
