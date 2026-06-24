-- VERSUS skeleton schema
-- Run:  mysql -u root -p versus < schema.sql
--
-- The four core tables for Phase I.
-- Students will extend with: predictions, votes, achievements,
-- user_achievements, follows, comments, plus triggers and a stored procedure.

DROP DATABASE IF EXISTS versus;
CREATE DATABASE versus;
USE versus;

CREATE TABLE Users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password      VARCHAR(255) NOT NULL,
    bio           TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Brackets (
    bracket_id           INT AUTO_INCREMENT PRIMARY KEY,
    host_id              INT NOT NULL,
    title                VARCHAR(255) NOT NULL,
    description          TEXT,
    entrant_count        INT NOT NULL,
    status               ENUM(
                             'draft',
                             'predictions_open',
                             'round_1','round_2','round_3','round_4','round_5',
                             'completed'
                         ) NOT NULL DEFAULT 'predictions_open',
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_entrant_count CHECK (entrant_count IN (4,8,16,32)),
    CONSTRAINT fk_brackets_host  FOREIGN KEY (host_id) REFERENCES Users(user_id)
);

CREATE TABLE Entrants (
    entrant_id   INT AUTO_INCREMENT PRIMARY KEY,
    bracket_id   INT NOT NULL,
    seed         INT NOT NULL,
    name         VARCHAR(255) NOT NULL,
    CONSTRAINT fk_entrants_bracket FOREIGN KEY (bracket_id) REFERENCES Brackets(bracket_id),
    CONSTRAINT uq_entrants_seed    UNIQUE (bracket_id, seed)
);

CREATE TABLE Matchups (
    matchup_id          INT AUTO_INCREMENT PRIMARY KEY,
    bracket_id          INT NOT NULL,
    round               INT NOT NULL,
    slot                INT NOT NULL,
    entrant_a_id        INT,
    entrant_b_id        INT,
    winner_entrant_id   INT,
    votes_a             INT NOT NULL DEFAULT 0,
    votes_b             INT NOT NULL DEFAULT 0,
    CONSTRAINT fk_matchups_bracket FOREIGN KEY (bracket_id)        REFERENCES Brackets(bracket_id),
    CONSTRAINT fk_matchups_a       FOREIGN KEY (entrant_a_id)      REFERENCES Entrants(entrant_id),
    CONSTRAINT fk_matchups_b       FOREIGN KEY (entrant_b_id)      REFERENCES Entrants(entrant_id),
    CONSTRAINT fk_matchups_winner  FOREIGN KEY (winner_entrant_id) REFERENCES Entrants(entrant_id),
    CONSTRAINT uq_matchups_slot    UNIQUE (bracket_id, round, slot)
);

CREATE TABLE Predictions (
    prediction_id      INT AUTO_INCREMENT PRIMARY KEY,
    user_id            INT NOT NULL,
    matchup_id         INT NOT NULL,
    picked_entrant_id  INT NOT NULL,
    correct_pick       BOOLEAN,
    points_earned      INT NOT NULL DEFAULT 0,
    submitted_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_predictions_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
    CONSTRAINT fk_predictions_matchup FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id),
    CONSTRAINT fk_predictions_pick FOREIGN KEY (picked_entrant_id) REFERENCES Entrants(entrant_id),
    CONSTRAINT uq_prediction_once UNIQUE (user_id, matchup_id),
    CONSTRAINT chk_prediction_points CHECK (points_earned >= 0)
);

CREATE TABLE Votes (
    vote_id      INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    matchup_id   INT NOT NULL,
    entrant_id   INT NOT NULL,
    voted_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_votes_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
    CONSTRAINT fk_votes_matchup FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id),
    CONSTRAINT fk_votes_entrant FOREIGN KEY (entrant_id) REFERENCES Entrants(entrant_id),
    CONSTRAINT uq_vote_once UNIQUE (user_id, matchup_id)
);

CREATE TABLE Achievements (
    achievement_code VARCHAR(50) PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    description      TEXT NOT NULL
);

CREATE TABLE User_Achievements (
    user_id           INT NOT NULL,
    achievement_code  VARCHAR(50) NOT NULL,
    earned_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, achievement_code),
    CONSTRAINT fk_user_achievements_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
    CONSTRAINT fk_user_achievements_achievement FOREIGN KEY (achievement_code) REFERENCES Achievements(achievement_code)
);

CREATE TABLE Follows (
    follower_id  INT NOT NULL,
    followed_id  INT NOT NULL,
    followed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (follower_id, followed_id),
    CONSTRAINT fk_follows_follower FOREIGN KEY (follower_id) REFERENCES Users(user_id),
    CONSTRAINT fk_follows_followed FOREIGN KEY (followed_id) REFERENCES Users(user_id),
    CONSTRAINT chk_no_self_follow CHECK (follower_id <> followed_id)
);

CREATE TABLE Comments (
    comment_id   INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    matchup_id   INT NOT NULL,
    body         TEXT NOT NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comments_user FOREIGN KEY (user_id) REFERENCES Users(user_id),
    CONSTRAINT fk_comments_matchup FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id)
);

INSERT INTO Achievements (achievement_code, name, description)
VALUES
('bracket_maker', 'Bracket Maker', 'Hosted the first bracket.'),
('locked_in', 'Locked In', 'Submitted 10 predictions.');

DELIMITER $$

CREATE PROCEDURE close_round(
    IN p_bracket_id INT,
    IN p_round INT
)
BEGIN
    DECLARE v_entrant_count INT;
    DECLARE v_max_round INT;
    DECLARE v_next_status VARCHAR(50);

    SELECT entrant_count
    INTO v_entrant_count
    FROM Brackets
    WHERE bracket_id = p_bracket_id;

    SET v_max_round = LOG2(v_entrant_count);

    START TRANSACTION;

    UPDATE Matchups
    SET winner_entrant_id =
        CASE
            WHEN votes_a >= votes_b THEN entrant_a_id
            ELSE entrant_b_id
        END
    WHERE bracket_id = p_bracket_id
      AND round = p_round;

    UPDATE Predictions p
    JOIN Matchups m
      ON p.matchup_id = m.matchup_id
    SET
        p.correct_pick =
            CASE
                WHEN p.picked_entrant_id = m.winner_entrant_id THEN TRUE
                ELSE FALSE
            END,
        p.points_earned =
            CASE
                WHEN p.picked_entrant_id = m.winner_entrant_id THEN p_round
                ELSE 0
            END
    WHERE m.bracket_id = p_bracket_id
      AND m.round = p_round;

    IF p_round < v_max_round THEN

        UPDATE Matchups next_m
        JOIN Matchups m1
          ON m1.bracket_id = next_m.bracket_id
         AND m1.round = p_round
         AND m1.slot = next_m.slot * 2 - 1
        JOIN Matchups m2
          ON m2.bracket_id = next_m.bracket_id
         AND m2.round = p_round
         AND m2.slot = next_m.slot * 2
        SET
            next_m.entrant_a_id = m1.winner_entrant_id,
            next_m.entrant_b_id = m2.winner_entrant_id
        WHERE next_m.bracket_id = p_bracket_id
          AND next_m.round = p_round + 1;

        SET v_next_status = CONCAT('round_', p_round + 1);

        UPDATE Brackets
        SET status = v_next_status
        WHERE bracket_id = p_bracket_id;

    ELSE

        UPDATE Brackets
        SET status = 'completed'
        WHERE bracket_id = p_bracket_id;

    END IF;

    COMMIT;
END $$

DELIMITER ;

CREATE INDEX idx_matchups_bracket_round
ON Matchups(bracket_id, round);

CREATE INDEX idx_predictions_user
ON Predictions(user_id);

CREATE INDEX idx_votes_matchup
ON Votes(matchup_id);

CREATE INDEX idx_comments_matchup
ON Comments(matchup_id);