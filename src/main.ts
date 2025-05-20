import fs from 'node:fs';
import path from 'node:path';
import { Client, Message, Events, GatewayIntentBits } from 'discord.js';
import { entersState, AudioPlayerStatus, createAudioPlayer, createAudioResource, joinVoiceChannel, StreamType, NoSubscriberBehavior, VoiceConnection } from '@discordjs/voice';
import dotenv from 'dotenv';

dotenv.config();

const soundPath: string = path.join(__dirname, 'sounds');
const soundFiles: string[] = fs.readdirSync(soundPath).filter(file => file.endsWith('.mp3'));
let soundFilePath: { [key: string]: string } = {};

for (const file of soundFiles) {
    const extractExtension: string = file.split('.')[0];
    const filePath: string = path.join(soundPath, file);
    soundFilePath[extractExtension] = filePath;
}

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildVoiceStates
    ]
});

let player = createAudioPlayer({
    behaviors: { noSubscriber: NoSubscriberBehavior.Pause }
});
let connection: VoiceConnection | null = null;

client.once(Events.ClientReady, (c: Client) => {
    console.log(`Ready! Logged in as ${c.user?.tag}`);
});

client.on(Events.MessageCreate, async (message: Message) => {
    if (message.author.bot) return;

    const args = message.content.split(' ');
    const command = args[0];
    const soundName = args[1];

    if (command === '!play' || command === '!play2') {
        if (!soundName || !soundFilePath[soundName]) {
            await message.reply('[ERR] Sound not found.');
            return;
        }

        const channel = message.member?.voice.channel;
        if (!channel) {
            await message.reply('[ERR] You need to be in a voice channel.');
            return;
        }

        if (!connection) {
            connection = joinVoiceChannel({
                adapterCreator: channel.guild.voiceAdapterCreator,
                channelId: channel.id,
                guildId: channel.guild.id,
                selfDeaf: true,
                selfMute: false,
            });
            connection.subscribe(player);
        }

        const resource = createAudioResource(soundFilePath[soundName], { inputType: StreamType.Arbitrary });
        player.play(resource);

        await entersState(player, AudioPlayerStatus.Playing, 10 * 1000);
        await message.reply(`[INFO] Playing: ${soundName}`);
    }

    if (command === '!stop') {
        if (player) {
            player.stop();
            await message.reply('[INFO] Stopped playback.');
        }
        if (connection) {
            connection.destroy();
            connection = null;
        }
    }
});

client.login(process.env.TOKEN);
