function restrict_access(){
    frappe.call({
        method: 'engineering.api.restrict_access',
        callback: function(r) {
            location.reload();
        }
    })
    
}

if (frappe.user.has_role("Local Admin")){
    frappe.db.get_value('Global Defaults', 'Global Defaults', 'restricted_access')
        .then(r => {
            let check = r.message.restricted_access;
            if (check == 0){
                $(window).load(function () {
                    $("#toolbar-help").append('<li><a href="#" onclick="restrict_access()">Restrict Access</a></li>');
                });
            }
        });
}