<?php

$BOT_TOKEN = getenv("8996911757:AAGT0uAy04NomLODfp1bNnFnuCHHBKHE5gI");

$API = "https://api.telegram.org/bot" . $BOT_TOKEN . "/";

function telegram($method, $data = [])
{
    global $API;

    $ch = curl_init($API . $method);

    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $data,
        CURLOPT_TIMEOUT => 20
    ]);

    $result = curl_exec($ch);
    curl_close($ch);

    return json_decode($result, true);
}

$update = json_decode(file_get_contents("php://input"), true);


// ==============================
// START
// ==============================

if (isset($update["message"]["text"])) {

    $chat_id = $update["message"]["chat"]["id"];
    $text = trim($update["message"]["text"]);

    if ($text === "/start") {

        $keyboard = [
            "inline_keyboard" => [
                [
                    [
                        "text" => "➕ Add Me To Your Group",
                        "url" => "https://t.me/YOUR_BOT_USERNAME?startgroup=true"
                    ]
                ],
                [
                    [
                        "text" => "ℹ️ Help",
                        "callback_data" => "help"
                    ]
                ]
            ]
        ];

        telegram("sendMessage", [
            "chat_id" => $chat_id,
            "text" =>
                "👋 <b>Welcome!</b>\n\n" .
                "আমি একটি Auto Approve Bot।\n\n" .
                "আমাকে আপনার Group-এ Admin করুন এবং Join Request এলে আমি automatically approve করব।\n\n" .
                "নিচের Button থেকে আমাকে আপনার Group-এ যোগ করুন।",
            "parse_mode" => "HTML",
            "reply_markup" => json_encode($keyboard)
        ]);
    }
}


// ==============================
// HELP BUTTON
// ==============================

if (isset($update["callback_query"])) {

    $callback_id = $update["callback_query"]["id"];
    $data = $update["callback_query"]["data"];

    telegram("answerCallbackQuery", [
        "callback_query_id" => $callback_id
    ]);

    if ($data === "help") {

        $chat_id = $update["callback_query"]["message"]["chat"]["id"];

        telegram("sendMessage", [
            "chat_id" => $chat_id,
            "text" =>
                "📖 <b>How To Use</b>\n\n" .
                "1️⃣ Add me to your group\n" .
                "2️⃣ Make me Admin\n" .
                "3️⃣ Enable Join Requests\n" .
                "4️⃣ I will automatically approve requests.",
            "parse_mode" => "HTML"
        ]);
    }
}


// ==============================
// JOIN REQUEST
// ==============================

if (isset($update["chat_join_request"])) {

    $request = $update["chat_join_request"];

    $group_id = $request["chat"]["id"];
    $group_name = $request["chat"]["title"] ?? "Group";

    $user_id = $request["from"]["id"];

    $first_name = $request["from"]["first_name"] ?? "User";


    // AUTO APPROVE
    telegram("approveChatJoinRequest", [
        "chat_id" => $group_id,
        "user_id" => $user_id
    ]);


    // USER NOTIFICATION
    telegram("sendMessage", [
        "chat_id" => $user_id,
        "text" =>
            "🔔 <b>Join Request</b>\n\n" .
            "আপনার <b>" .
            htmlspecialchars($group_name, ENT_QUOTES, "UTF-8") .
            "</b>-এর Join Request পাওয়া গেছে।\n\n" .
            "✅ আপনার Request automatically approved হয়েছে।",
        "parse_mode" => "HTML"
    ]);
}


echo "OK";
