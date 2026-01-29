// ===== CLIENT-SIDE AI USING REAL DATABASE DATA =====
// This file handles AI functionality without external API calls
// All data is fetched from the database via local API endpoints

let realData = {
    clients: null,
    invoices: null,
    stats: null
};

// Fetch real data from database on page load
async function loadRealData() {
    try {
        // Fetch all data in parallel
        const [clientsRes, invoicesRes, statsRes] = await Promise.all([
            fetch('/api/data/clients'),
            fetch('/api/data/invoices'),
            fetch('/api/data/stats')
        ]);

        realData.clients = await clientsRes.json();
        realData.invoices = await invoicesRes.json();
        realData.stats = await statsRes.json();

        console.log('✅ Real data loaded:', realData);
    } catch (error) {
        console.error('❌ Error loading real data:', error);
    }
}

// Process AI queries using real database data
function processAIQuery(query) {
    const q = query.toLowerCase().trim();

    // Client queries
    if (q.includes('client')) {
        if (q.includes('how many') || q.includes('total') || q.includes('count')) {
            return `You have ${realData.clients.total} clients in total.`;
        }
        if (q.includes('active')) {
            return `You have ${realData.clients.active} active clients.`;
        }
        if (q.includes('inactive')) {
            return `You have ${realData.clients.inactive} inactive clients.`;
        }
        if (q.includes('list') || q.includes('name')) {
            const names = realData.clients.clients.map(c => c.name).slice(0, 10);
            return `Here are your clients: ${names.join(', ')}${realData.clients.total > 10 ? '...' : ''}`;
        }
    }

    // Invoice queries
    if (q.includes('invoice')) {
        if (q.includes('how many') || q.includes('total') || q.includes('count')) {
            return `You have ${realData.invoices.total} invoices in total.`;
        }
        if (q.includes('paid')) {
            return `${realData.invoices.paid} invoices have been paid.`;
        }
        if (q.includes('unpaid') || q.includes('pending')) {
            return `${realData.invoices.unpaid} invoices are unpaid.`;
        }
    }

    // Revenue queries
    if (q.includes('revenue') || q.includes('income')) {
        if (q.includes('today')) {
            return `Today's revenue is ₹${realData.stats.revenue.today.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
        }
        if (q.includes('week')) {
            return `This week's revenue is ₹${realData.stats.revenue.week.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
        }
        if (q.includes('month')) {
            return `This month's revenue is ₹${realData.stats.revenue.month.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
        }
    }

    // Outstanding queries
    if (q.includes('outstanding') || q.includes('pending payment')) {
        return `Outstanding amount is ₹${realData.stats.outstanding.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    }

    // Default response
    return "I can help you with information about clients, invoices, revenue, and outstanding payments. Try asking 'How many clients do I have?' or 'What is today's revenue?'";
}

// Voice command processing (client-side pattern matching)
function processVoiceCommand(command) {
    const cmd = command.toLowerCase().trim();

    // Navigate commands
    if (cmd.includes('dashboard') || cmd.includes('home')) {
        window.location.href = '/dashboard';
        return { success: true, message: 'Navigating to dashboard' };
    }
    if (cmd.includes('invoice') && (cmd.includes('create') || cmd.includes('new'))) {
        window.location.href = '/create_invoice';
        return { success: true, message: 'Opening invoice creation' };
    }
    if (cmd.includes('client') && (cmd.includes('create') || cmd.includes('new'))) {
        window.location.href = '/create_client';
        return { success: true, message: 'Opening client creation' };
    }
    if (cmd.includes('analytics') || cmd.includes('report')) {
        window.location.href = '/analytics';
        return { success: true, message: 'Opening analytics' };
    }

    // Data queries - use AI processing
    const response = processAIQuery(cmd);
    return { success: true, message: response };
}

// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadRealData);
} else {
    loadRealData();
}

// Export functions for use in other scripts
window.AILocal = {
    processQuery: processAIQuery,
    processVoiceCommand: processVoiceCommand,
    getRealData: () => realData,
    refreshData: loadRealData
};
