const { app } = require('@azure/functions');
const { query } = require('../libs/database');

async function activateScheduledBots(myTimer, context) {
    context.log('Checking for scheduled chatbots to activate...');
    try {
        const result = await query(`
            UPDATE chatbot
            SET is_active = true
            WHERE is_active = false 
                AND publish_date IS NOT NULL 
                    AND publish_date <= NOW()
                RETURNING id, name;
        `);

        if (result && result.rowCount > 0) {
            context.log('Scheduled chatbots activated successfully.');
            result.rows.forEach(bot => {
                context.log(`Activated chatbot - ID: ${bot.id}, Name: ${bot.name}`);
            });
        } else {
            context.log('No current chatbot need to be activated');
        }
    } catch (error) {
        context.error('Error activating scheduled bots due to database error:', error);
        context.error('Stack trace:', error.stack || error);
    }
}

// Runs every 1 minute
app.timer('activateScheduledBots', {
    schedule: '0 * * * * *',
    handler: activateScheduledBots
});
