document.addEventListener('DOMContentLoaded', () => {
    const deleteButtons = document.querySelectorAll('.delete-operation-button');

    deleteButtons.forEach(button => {
        button.addEventListener('click', function(event) {
            event.preventDefault();
            
            const form = this.closest('form');
            const confirmation = confirm('Es-tu sûr de vouloir supprimer cette opération ?');
            
            if (confirmation) {
                fetch(form.action, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ id: form.dataset.id }) // Envoie l'ID de l'opération
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload(); // Recharge la page pour voir la suppression
                    } else {
                        alert('Erreur lors de la suppression de l\'opération');
                    }
                })
                .catch(() => {
                    alert('Erreur réseau, l\'opération n\'a pas pu être supprimée');
                });
            }
        });
    });
});
