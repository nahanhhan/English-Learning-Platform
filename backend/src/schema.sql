-- 与现有学习数据库兼容的 SQLite 表结构。

CREATE TABLE IF NOT EXISTS accumulation_groups (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	name VARCHAR(200) NOT NULL,
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS accumulation_sessions (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	scope VARCHAR(100) NOT NULL,
	source VARCHAR(10) NOT NULL,
	cursor INTEGER NOT NULL,
	version INTEGER NOT NULL,
	updated_at DATETIME NOT NULL,
	receipts TEXT NOT NULL,
	UNIQUE (scope)
);

CREATE TABLE IF NOT EXISTS ai_providers (
	id INTEGER NOT NULL,
	name VARCHAR(60) NOT NULL,
	base_url VARCHAR(200) NOT NULL,
	api_key VARCHAR(300) NOT NULL,
	model VARCHAR(100) NOT NULL,
	is_default BOOLEAN NOT NULL,
	service_type VARCHAR(30) NOT NULL,
	reasoning_mode VARCHAR(12) NOT NULL,
	reasoning_effort VARCHAR(20) NOT NULL,
	models_json TEXT NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS classroom_groups (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	name VARCHAR(200) NOT NULL,
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS classroom_sessions (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	scope VARCHAR(100) NOT NULL,
	source VARCHAR(10) NOT NULL,
	cursor INTEGER NOT NULL,
	version INTEGER NOT NULL,
	updated_at DATETIME NOT NULL,
	receipts TEXT NOT NULL,
	UNIQUE (scope)
);

CREATE TABLE IF NOT EXISTS phrases (
	id INTEGER NOT NULL,
	book VARCHAR(20) NOT NULL,
	text VARCHAR(200) NOT NULL,
	translation TEXT NOT NULL,
	note TEXT NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_phrases_book ON phrases (book);

CREATE INDEX IF NOT EXISTS ix_phrases_text ON phrases (text);

CREATE TABLE IF NOT EXISTS questions (
	id INTEGER NOT NULL,
	exam_type VARCHAR(10) NOT NULL,
	year INTEGER NOT NULL,
	month INTEGER NOT NULL,
	set_no INTEGER NOT NULL,
	q_type VARCHAR(20) NOT NULL,
	title VARCHAR(200) NOT NULL,
	prompt TEXT NOT NULL,
	source_text TEXT NOT NULL,
	chart_image VARCHAR(300) NOT NULL,
	source_file VARCHAR(300) NOT NULL,
	notes VARCHAR(300) NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_questions_exam_type ON questions (exam_type);

CREATE INDEX IF NOT EXISTS ix_questions_q_type ON questions (q_type);

CREATE INDEX IF NOT EXISTS ix_questions_year ON questions (year);

CREATE TABLE IF NOT EXISTS short_questions (
	id VARCHAR(40) NOT NULL,
	topic VARCHAR(80) NOT NULL,
	title VARCHAR(200) NOT NULL,
	data_json TEXT NOT NULL,
	batch VARCHAR(60) NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_short_questions_topic ON short_questions (topic);

CREATE TABLE IF NOT EXISTS srs_cards (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	item_type VARCHAR(10) NOT NULL,
	item_id INTEGER NOT NULL,
	book VARCHAR(20) NOT NULL,
	status VARCHAR(10) NOT NULL,
	ease FLOAT NOT NULL,
	interval_days FLOAT NOT NULL,
	due DATE NOT NULL,
	reps INTEGER NOT NULL,
	lapses INTEGER NOT NULL,
	starred BOOLEAN NOT NULL,
	in_mistake_book BOOLEAN NOT NULL,
	mistake_consec INTEGER NOT NULL,
	added_at DATE NOT NULL,
	last_review_at DATETIME
);

CREATE INDEX IF NOT EXISTS ix_srs_cards_book ON srs_cards (book);

CREATE INDEX IF NOT EXISTS ix_srs_cards_due ON srs_cards (due);

CREATE INDEX IF NOT EXISTS ix_srs_cards_item_id ON srs_cards (item_id);

CREATE INDEX IF NOT EXISTS ix_srs_cards_item_type ON srs_cards (item_type);

CREATE TABLE IF NOT EXISTS user_settings (
	"key" VARCHAR(60) NOT NULL,
	value TEXT NOT NULL,
	PRIMARY KEY ("key")
);

CREATE TABLE IF NOT EXISTS words (
	id INTEGER NOT NULL,
	book VARCHAR(20) NOT NULL,
	headword VARCHAR(80) NOT NULL,
	phonetic_us VARCHAR(80) NOT NULL,
	phonetic_uk VARCHAR(80) NOT NULL,
	translation TEXT NOT NULL,
	definition TEXT NOT NULL,
	tags VARCHAR(200) NOT NULL,
	freq INTEGER NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_words_book ON words (book);

CREATE INDEX IF NOT EXISTS ix_words_headword ON words (headword);

CREATE TABLE IF NOT EXISTS accumulation_entries (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	group_id INTEGER NOT NULL,
	item_type VARCHAR(10) NOT NULL,
	english VARCHAR(300) NOT NULL,
	normalized VARCHAR(300) NOT NULL,
	translation TEXT NOT NULL,
	source TEXT NOT NULL,
	in_mistake_book BOOLEAN NOT NULL,
	mistake_consec INTEGER NOT NULL,
	completed INTEGER NOT NULL,
	UNIQUE (group_id, item_type, normalized),
	FOREIGN KEY(group_id) REFERENCES accumulation_groups (id)
);

CREATE INDEX IF NOT EXISTS ix_accumulation_entries_group_id ON accumulation_entries (group_id);

CREATE TABLE IF NOT EXISTS accumulation_session_items (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	session_id INTEGER NOT NULL,
	entry_id INTEGER NOT NULL,
	position INTEGER NOT NULL,
	snapshot TEXT NOT NULL,
	options TEXT NOT NULL,
	stage VARCHAR(10) NOT NULL,
	picked TEXT,
	spell_wrong BOOLEAN NOT NULL,
	rating VARCHAR(10) NOT NULL,
	UNIQUE (session_id, position),
	FOREIGN KEY(session_id) REFERENCES accumulation_sessions (id)
);

CREATE INDEX IF NOT EXISTS ix_accumulation_session_items_entry_id ON accumulation_session_items (entry_id);

CREATE INDEX IF NOT EXISTS ix_accumulation_session_items_session_id ON accumulation_session_items (session_id);

CREATE TABLE IF NOT EXISTS classroom_entries (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	group_id INTEGER NOT NULL,
	item_type VARCHAR(10) NOT NULL,
	english VARCHAR(300) NOT NULL,
	normalized VARCHAR(300) NOT NULL,
	translation TEXT NOT NULL,
	source TEXT NOT NULL,
	in_mistake_book BOOLEAN NOT NULL,
	mistake_consec INTEGER NOT NULL,
	completed INTEGER NOT NULL,
	UNIQUE (group_id, item_type, normalized),
	FOREIGN KEY(group_id) REFERENCES classroom_groups (id)
);

CREATE INDEX IF NOT EXISTS ix_classroom_entries_group_id ON classroom_entries (group_id);

CREATE TABLE IF NOT EXISTS classroom_session_items (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	session_id INTEGER NOT NULL,
	entry_id INTEGER NOT NULL,
	position INTEGER NOT NULL,
	snapshot TEXT NOT NULL,
	options TEXT NOT NULL,
	stage VARCHAR(10) NOT NULL,
	picked TEXT,
	spell_wrong BOOLEAN NOT NULL,
	rating VARCHAR(10) NOT NULL,
	UNIQUE (session_id, position),
	FOREIGN KEY(session_id) REFERENCES classroom_sessions (id)
);

CREATE INDEX IF NOT EXISTS ix_classroom_session_items_entry_id ON classroom_session_items (entry_id);

CREATE INDEX IF NOT EXISTS ix_classroom_session_items_session_id ON classroom_session_items (session_id);

CREATE TABLE IF NOT EXISTS review_logs (
	id INTEGER NOT NULL,
	card_id INTEGER NOT NULL,
	item_type VARCHAR(10) NOT NULL,
	rating VARCHAR(10) NOT NULL,
	last_interval FLOAT NOT NULL,
	next_interval FLOAT NOT NULL,
	reviewed_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(card_id) REFERENCES srs_cards (id)
);

CREATE INDEX IF NOT EXISTS ix_review_logs_card_id ON review_logs (card_id);

CREATE INDEX IF NOT EXISTS ix_review_logs_reviewed_at ON review_logs (reviewed_at);

CREATE TABLE IF NOT EXISTS short_progress (
	question_id VARCHAR(40) NOT NULL,
	in_review BOOLEAN NOT NULL,
	streak INTEGER NOT NULL,
	last_count_date DATE,
	PRIMARY KEY (question_id),
	FOREIGN KEY(question_id) REFERENCES short_questions (id)
);

CREATE TABLE IF NOT EXISTS short_runs (
	id VARCHAR(40) NOT NULL,
	question_id VARCHAR(40) NOT NULL,
	snapshot TEXT NOT NULL,
	is_review BOOLEAN NOT NULL,
	review_applied BOOLEAN NOT NULL,
	version INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(question_id) REFERENCES short_questions (id)
);

CREATE INDEX IF NOT EXISTS ix_short_runs_question_id ON short_runs (question_id);

CREATE TABLE IF NOT EXISTS submissions (
	id INTEGER NOT NULL,
	question_id INTEGER,
	exam_type VARCHAR(10) NOT NULL,
	q_type VARCHAR(20) NOT NULL,
	title VARCHAR(200) NOT NULL,
	prompt TEXT NOT NULL,
	source_text TEXT NOT NULL,
	content TEXT NOT NULL,
	word_count INTEGER NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(question_id) REFERENCES questions (id)
);

CREATE TABLE IF NOT EXISTS accumulation_review_logs (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	entry_id INTEGER NOT NULL,
	session_id INTEGER NOT NULL,
	question_id INTEGER NOT NULL,
	choice_correct BOOLEAN NOT NULL,
	spelling_correct BOOLEAN NOT NULL,
	completed_at DATETIME NOT NULL,
	FOREIGN KEY(entry_id) REFERENCES accumulation_entries (id),
	UNIQUE (question_id)
);

CREATE INDEX IF NOT EXISTS ix_accumulation_review_logs_completed_at ON accumulation_review_logs (completed_at);

CREATE INDEX IF NOT EXISTS ix_accumulation_review_logs_entry_id ON accumulation_review_logs (entry_id);

CREATE TABLE IF NOT EXISTS gradings (
	id INTEGER NOT NULL,
	submission_id INTEGER NOT NULL,
	provider VARCHAR(60) NOT NULL,
	model VARCHAR(100) NOT NULL,
	mock BOOLEAN NOT NULL,
	score FLOAT NOT NULL,
	full_score FLOAT NOT NULL,
	result_json TEXT NOT NULL,
	error TEXT NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(submission_id) REFERENCES submissions (id)
);

CREATE INDEX IF NOT EXISTS ix_gradings_submission_id ON gradings (submission_id);

CREATE TABLE IF NOT EXISTS short_attempts (
	id INTEGER NOT NULL,
	run_id VARCHAR(40) NOT NULL,
	request_id VARCHAR(100) NOT NULL,
	content TEXT NOT NULL,
	requested_provider_id INTEGER,
	provider_id INTEGER,
	profile_json TEXT NOT NULL,
	is_revision BOOLEAN NOT NULL,
	status VARCHAR(12) NOT NULL,
	score FLOAT NOT NULL,
	result_json TEXT NOT NULL,
	error TEXT NOT NULL,
	mock BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id) REFERENCES short_runs (id),
	UNIQUE (request_id)
);

CREATE INDEX IF NOT EXISTS ix_short_attempts_run_id ON short_attempts (run_id);
